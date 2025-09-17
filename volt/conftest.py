# import logging
# import os
# import sys
# from subprocess import PIPE, run
# from types import FunctionType
# from pathlib import Path
# from subprocess import STDOUT, check_output
#
# from volt import zig_types, SRC
#
# # SRC = zig_types.lib._name
#
# log = logging.getLogger('volt.py')
#
# class SegmentationFault(Exception):
#     pass
#
#
# class CUnitTestFailure(Exception):
#     pass
#
#
# def pytest_pycollect_makeitem(collector, name, obj):
#     if (
#         not os.getenv("PYTEST_CUNIT")
#         and isinstance(obj, FunctionType)
#         and name.startswith("test_")
#     ):
#         obj.__cunit__ = (str(collector.fspath), name)
#
#
# def cunit(module: str, name: str, full_name: str):
#     def _(*_, **__):
#         test = f"{module}::{name}"
#         env = os.environ.copy()
#         env["PYTEST_CUNIT"] = full_name
#
#         # result = run([sys.argv[0], "-svv", test], stdout=PIPE, stderr=PIPE, env=env)
#         result = run([sys.argv[0], "-svv", test], env=env)
#
#         log.debug(f"rc: {result.returncode}")
#
#         match result.returncode:
#             case 0:
#                 return
#
#             case -11:
#                 # binary_name = Path(module).stem.replace("test_", "")
#                 binary_name = Path(zig_types.lib._name)
#                 path = (SRC / binary_name).with_suffix(".so")
#                 log.debug(f"PATH: {path}")
#                 raise SegmentationFault(bt(path))
#
#             # case -6:
#             #     # binary_name = Path(module).stem.replace("test_", "")
#             #     binary_name = Path(zig_types.lib._name)
#             #     path = (SRC / binary_name).with_suffix(".so")
#             #     print(f"PATH: {path}")
#             #     raise SegmentationFault(bt(path))
#             # case _:
#             #     binary_name = Path(module).stem.replace("test_", "")
#             #     raise SegmentationFault(bt((SRC / binary_name).with_suffix(".so")))
#
#
#         raise CUnitTestFailure("\n" + result.stdout.decode())
#
#     return _
#
# def pytest_collection_modifyitems(session, config, items) -> None:
#     if test_name := os.getenv("PYTEST_CUNIT"):
#         # We are inside the sandbox process. We select the only test we care
#         items[:] = [_ for _ in items if _.name == test_name]
#         return
#
#     for item in items:
#         if hasattr(item._obj, "__cunit__"):
#             item._obj = cunit(*item._obj.__cunit__, full_name=item.name)
#
#
#
# def gdb(cmds: list[str], *args: str) -> str:
#     return check_output(
#         ["gdb", "-q", "-batch"]
#         + [_ for cs in (("-ex", _) for _ in cmds) for _ in cs]
#         + list(args),
#         stderr=STDOUT,
#     ).decode()
#
#
# def bt(binary: Path) -> str:
#     if Path("core").is_file():
#         return gdb(["bt full", "q"], str(binary), "core")
#     return "No core dump available."
