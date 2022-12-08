from aiohttp import web
from src.views import WebSocketHandler
from envparse import env
from asyncpg import create_pool
import os

env.read_envfile('.env')

routes = [
    web.get('/ws', WebSocketHandler().dispatch)
]


async def init():
    app = web.Application()
    app.add_routes(routes)
    app['ws_connections'] = {}
    app['pool'] = await create_pool(f'postgresql://{os.environ.get("DB_USER")}:{os.environ.get("DB_PASS")}@{os.environ.get("DB_HOST")}:{os.environ.get("DB_PORT")}/{os.environ.get("DB_NAME")}')
    return app


if __name__ == '__main__':
    web.run_app(init(), host='127.0.0.1', port=8081)
