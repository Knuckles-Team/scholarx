import asyncio
import sys
import threading

from agent_connector_sdk.runner.cli import main
from epistemic_graph import EpistemicGraphClient
from live_engine import _SECRET, GRAPH, TENANT, _context
from paper_support import catalog as _catalog
from paper_support import mutation_context as _mutation_context

loop = asyncio.new_event_loop()
thread = threading.Thread(target=loop.run_forever, daemon=True)
thread.start()
future = asyncio.run_coroutine_threadsafe(
    EpistemicGraphClient.connect(
        socket_path=sys.argv[1], auth_secret=_SECRET, graph_name=GRAPH, verified_context=_context(["test"], ["*"])
    ),
    loop,
)
client = future.result(30)


class Proxy:
    async def _send(self, *args, **kwargs):
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(client._send(*args, **kwargs), loop))

    async def supports(self, method):
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(client.supports(method), loop))


async def authority(connector):
    return _catalog(), _mutation_context().model_copy(update={"tenant_id": TENANT})


try:
    result = main(
        ["--config", sys.argv[2], "--once", "--log-format", "text"],
        sink_client=Proxy(),
        pack_import_authority=authority,
        decide_tenant=TENANT,
    )
finally:
    asyncio.run_coroutine_threadsafe(client.close(), loop).result(30)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(10)
sys.exit(result)
