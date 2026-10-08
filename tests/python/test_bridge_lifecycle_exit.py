"""Bridge lifecycle must release real listeners, loops and threads before exit."""

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("websockets")

SOURCE = Path(__file__).resolve().parents[2] / "python/auroraview/integration/bridge.py"
CHILD = r"""
import asyncio,atexit,contextlib,importlib.util,json,socket,sys,threading,time
spec=importlib.util.spec_from_file_location('owned_bridge',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
Bridge=module.Bridge
case=sys.argv[2]
started=time.monotonic()
def port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));return probe.getsockname()[1]
def released(value):
    with socket.socket() as probe:probe.bind(('127.0.0.1',value))
async def running(bridge):
    for _ in range(200):
        if bridge.is_running:return
        await asyncio.sleep(.005)
    raise AssertionError('Bridge did not become ready')
async def direct(cancel=False):
    bridge=Bridge(host='127.0.0.1',port=port())
    task=asyncio.create_task(bridge.start())
    await running(bridge)
    await asyncio.sleep(.02)
    if cancel:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):await task
    else:
        await bridge.stop()
        await asyncio.wait_for(asyncio.shield(task),1)
    assert not bridge.is_running
    assert not bridge.clients
    assert task.done()
    released(bridge.port)
if case in ('normal','cancel'):
    asyncio.run(direct(case=='cancel'))
elif case=='background':
    bridge=Bridge(host='127.0.0.1',port=port())
    for iteration in range(3):
        bridge.start_background()
        thread,loop=bridge._thread,bridge._loop
        bridge.start_background()
        assert bridge._thread is thread
        asyncio.run(bridge.stop())
        thread.join(.2)
        assert not thread.is_alive(),'Bridge background thread survived stop()'
        assert loop.is_closed(),'Bridge background event loop remained open'
        assert not bridge.is_running
        released(bridge.port)
elif case=='bind_failure':
    with socket.socket() as blocker:
        blocker.bind(('127.0.0.1',0));blocker.listen()
        bridge=Bridge(host='127.0.0.1',port=blocker.getsockname()[1])
        try:bridge.start_background()
        except OSError:pass
        else:raise AssertionError('Bridge hid listener bind failure')
        assert not bridge.is_running
        assert not bridge._thread.is_alive()
        assert bridge._loop.is_closed()
        assert not bridge._atexit_registered,'Failed startup retained an exit-hook owner'
    bridge.start_background();asyncio.run(bridge.stop());released(bridge.port)
elif case=='client_cancel':
    async def run():
        bridge=Bridge(host='127.0.0.1',port=port())
        entered=asyncio.Event()
        @bridge.on('block')
        async def block(data,client):
            entered.set();await asyncio.Future()
        task=asyncio.create_task(bridge.start());await running(bridge)
        async with module.websockets.connect(f'ws://127.0.0.1:{bridge.port}') as client:
            await client.send(json.dumps({'action':'block'}))
            await asyncio.wait_for(entered.wait(),1)
            await asyncio.wait_for(bridge.stop(),2)
            await asyncio.wait_for(task,1)
        assert not bridge.clients
    asyncio.run(run())
elif case=='stop_cancel':
    class Discovery:
        def start(self,metadata):pass
        def stop(self):time.sleep(.05)
    bridge=Bridge(host='127.0.0.1',port=port())
    bridge._service_discovery=Discovery()
    bridge.start_background()
    thread,loop=bridge._thread,bridge._loop
    async def run():
        stopping=asyncio.create_task(bridge.stop())
        await asyncio.sleep(.005)
        stopping.cancel()
        with contextlib.suppress(asyncio.CancelledError):await stopping
        await bridge.stop()
    asyncio.run(run())
    assert not thread.is_alive()
    assert loop.is_closed()
    released(bridge.port)
elif case=='handler_stop':
    async def run():
        bridge=Bridge(host='127.0.0.1',port=port())
        @bridge.on('stop')
        async def stop(data,client):await bridge.stop()
        task=asyncio.create_task(bridge.start());await running(bridge)
        async with module.websockets.connect(f'ws://127.0.0.1:{bridge.port}') as client:
            await client.send(json.dumps({'action':'stop'}))
            await asyncio.wait_for(task,2)
        assert not bridge.clients
    asyncio.run(run())
elif case=='auto_exit':
    def verify_exit():
        assert not bridge._thread.is_alive(),'Exit hook did not join its thread'
        assert bridge._loop.is_closed(),'Exit hook did not close its event loop'
        assert not bridge.clients,'Exit hook did not close its client'
        assert not bridge._atexit_registered
        released(bridge.port)
        print(json.dumps({'case':case,'elapsed':time.monotonic()-started,'exit_cleanup':True}))
    atexit.register(verify_exit)
    bridge=Bridge(host='127.0.0.1',port=port(),auto_start=True)
    async def connect():return await module.websockets.connect(f'ws://127.0.0.1:{bridge.port}')
    client=asyncio.run_coroutine_threadsafe(connect(),bridge._loop).result(2)
    assert bridge.client_count==1
else:raise AssertionError(case)
if case!='auto_exit':
    assert not [t for t in threading.enumerate() if t.name.startswith('AuroraViewBridge')]
    print(json.dumps({'case':case,'elapsed':time.monotonic()-started,'threads':len(threading.enumerate())}))
"""


@pytest.mark.parametrize(
    "case",
    [
        "normal",
        "cancel",
        "background",
        "bind_failure",
        "client_cancel",
        "stop_cancel",
        "handler_stop",
        "auto_exit",
    ],
)
def test_bridge_releases_owned_resources_in_bounded_process(case):
    result = subprocess.run(
        [sys.executable, "-W", "error::ResourceWarning", "-c", CHILD, str(SOURCE), case],
        capture_output=True,
        text=True,
        timeout=12,
    )
    assert result.returncode == 0, f"{case}:\n{result.stdout}\n{result.stderr}"
    assert '"elapsed"' in result.stdout
    assert "Task was destroyed" not in result.stderr
    assert "Exception ignored" not in result.stderr
    assert "Exception in thread" not in result.stderr
