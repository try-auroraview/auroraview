"""Run borrowed backend calls without constructing a renderer or a server.

Replace DemoBackend's public call_tool/list_tools/subscribe with an existing
MCP client or public host adapter. Async calls stay on your existing event loop.
Each view can own one borrowed session; closing it does not stop the backend.
This example binds no WebView methods because attachment needs a public,
removable binding contract as well as a renderer owner-thread dispatcher.
"""

import json

from auroraview.integration.backend import BackendSession


class DemoBackend:
    def __init__(self):
        self.listeners = []

    def call_tool(self, name, params):
        if name != "scene.selection":
            raise KeyError(name)
        return {"content": [{"type": "text", "text": json.dumps(params)}], "isError": False}

    def list_tools(self):
        return [{"name": "scene.selection", "inputSchema": {"type": "object"}}]

    def subscribe(self, event, handler):
        item = (event, handler)
        self.listeners.append(item)
        return lambda: self.listeners.remove(item)

    def publish(self, event, payload):
        for name, handler in tuple(self.listeners):
            if name == event:
                handler(payload)


def main():
    backend = DemoBackend()
    first = BackendSession.borrow(
        invoke_tool=backend.call_tool, list_tools=backend.list_tools, subscribe=backend.subscribe
    )
    second = BackendSession.borrow(
        invoke_tool=backend.call_tool, list_tools=backend.list_tools, subscribe=backend.subscribe
    )
    received = []
    first.on("scene.changed", lambda payload: received.append(["first", payload]))
    second.on("scene.changed", lambda payload: received.append(["second", payload]))
    print(json.dumps(first.tools()))
    print(json.dumps(first.call("scene.selection", {"names": ["Cube"]})))
    first.close()
    backend.publish("scene.changed", {"names": ["Sphere"]})
    print(json.dumps(received))  # Only the remaining view receives the existing backend event.
    print(json.dumps(second.call("scene.selection", {"names": ["Sphere"]})))
    second.close()


if __name__ == "__main__":
    main()
