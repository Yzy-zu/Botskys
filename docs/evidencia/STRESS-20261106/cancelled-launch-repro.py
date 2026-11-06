import asyncio
import faulthandler
from unittest.mock import patch
from botsky.engines.process import run_process

faulthandler.dump_traceback_later(1, repeat=False)
async def main():
    launches=[]
    async def pending_launch(*args, **kwargs):
        launches.append(asyncio.current_task())
        await asyncio.Event().wait()
    with patch("asyncio.create_subprocess_exec", pending_launch):
        task=asyncio.create_task(run_process(["synthetic-no-child"], 1))
        while not launches:
            await asyncio.sleep(0)
        launches[0].cancel()
        await task
asyncio.run(main())
