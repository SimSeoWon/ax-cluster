"""`python -m master.task_queue ...` 진입점."""
if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["--serve"]:
        # #897: server import 전에 기록한다. stdio MCP·조회 CLI 출력은 보존한다.
        from ..service_freshness import record_startup
        record_startup("ax-task-queue")

from .server import main

if __name__ == "__main__":
    main()
