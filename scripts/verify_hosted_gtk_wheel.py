"""Check experimental wheel identity; importing it does not prove GUI support."""

import argparse
import hashlib
import importlib
import importlib.machinery
import importlib.util
import json
import sysconfig
import zipfile
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_imported_modules(archive, library_root, package, native, hosted):
    """Reject imported files that are absent from, or differ from, this wheel."""
    members = set(archive.namelist())
    for module in (package, native, hosted):
        path = Path(module.__file__).resolve()
        member = path.relative_to(library_root).as_posix()
        if member not in members or path.read_bytes() != archive.read(member):
            raise RuntimeError("Imported module differs from exact wheel: " + member)
    native_path = Path(native.__file__).resolve()
    spec = getattr(native, "__spec__", None)
    if spec is None or not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader):
        raise RuntimeError("Imported native module is not loaded by ExtensionFileLoader")
    if Path(spec.origin).resolve() != native_path:
        raise RuntimeError("Native import origin differs from its module file")
    if not any(
        str(native_path).endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES
    ):
        raise RuntimeError("Imported native module lacks a recognized extension suffix")


def inspect_wheel(root, installed=False):
    wheels = sorted((root / "dist/hosted-gtk").glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected exactly one freshly built hosted GTK wheel")
    wheel = wheels[0]
    report = {"wheel": wheel.name, "sha256": digest(wheel.read_bytes())}
    with zipfile.ZipFile(wheel) as archive:
        members = [
            name
            for name in archive.namelist()
            if name.startswith("auroraview/") and not name.endswith("/")
        ]
        if not members or len(members) != len(set(members)):
            raise RuntimeError("Missing or duplicated AuroraView wheel payload")
        python_files = list((root / "python/auroraview").rglob("*.py"))
        for source in python_files:
            member = source.relative_to(root / "python").as_posix()
            if archive.read(member) != source.read_bytes():
                raise RuntimeError("Wheel does not match checked-out Python source: " + member)
        report["matching_source_files"] = len(python_files)
        if installed:
            package = importlib.import_module("auroraview")
            native = importlib.import_module("auroraview._core")
            hosted = importlib.import_module("auroraview.hosted")
            if not hasattr(native, "HostRuntime"):
                raise RuntimeError("Installed extension lacks experimental HostRuntime")
            package_root = Path(package.__file__).resolve().parent
            library_root = package_root.parent
            expected_roots = {
                Path(sysconfig.get_path(name)).resolve() for name in ("purelib", "platlib")
            }
            if library_root not in expected_roots:
                raise RuntimeError(
                    "AuroraView was imported outside this environment's site-packages"
                )
            for module in (native, hosted):
                Path(module.__file__).resolve().relative_to(package_root)
            verify_imported_modules(archive, library_root, package, native, hosted)
            for member in members:
                path = (library_root / member).resolve()
                path.relative_to(package_root)
                if path.read_bytes() != archive.read(member):
                    raise RuntimeError("Installed file differs from exact wheel: " + member)
            # tests/conftest.py adds source paths only when this lookup fails.
            if importlib.util.find_spec("auroraview._core") is None:
                raise RuntimeError("Regression conftest would select source fallback")
            report.update(
                installed_package=str(package_root),
                installed_native=str(Path(native.__file__).resolve()),
                matching_installed_files=len(members),
                regression_conftest_source_fallback=False,
            )
    report["native_gui_acceptance"] = False
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(inspect_wheel(root, installed=arguments.installed), indent=2))


if __name__ == "__main__":
    main()
