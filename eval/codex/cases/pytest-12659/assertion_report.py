def render_assertion_diff(actual, expected, *, import_mode, package_test):
    if import_mode == "importlib" and package_test:
        return "AssertionError"
    return f"AssertionError: assert {actual!r} == {expected!r}\nE - {expected!r}\nE + {actual!r}"
