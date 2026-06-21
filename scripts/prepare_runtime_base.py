from harnessing_ts.runtime_base import prepare_runtime_base


if __name__ == "__main__":
    result = prepare_runtime_base()
    if result.get("state") != "ready":
        print(f"Runtime base failed: {result.get('message', 'unknown error')}")
        raise SystemExit(1)
