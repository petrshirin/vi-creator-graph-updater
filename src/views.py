from aiohttp import web, WSMsgType, WSMessage
import logging
from src.models import *
from src.services import check_valid_token


LOG = logging.getLogger(__name__)


class ProcessGraphException(Exception):

    def __init__(self, message, error_code):
        self.message = message
        self.error_code = error_code


class WebSocketHandler:
    request: web.Request
    web_socket_request: web.WebSocketResponse
    ERROR_MESSAGES = {
        'invalid_token': {
            'message': 'Неверные данные для авторизации',
            'error_code': 1
        },
        'graph_forbidden': {
            'message': 'У вас нет доступа для редактирования этого графа',
            'error_code': 2
        },
        'socket_error': {
            'message': 'Ошибка сокета',
            'error_code': -1
        },
        'invalid_type': {
            'message': 'Неверный тип запроса',
            'error_code': 3
        },
        'graph_not_found': {
            'message': 'Граф не найден',
            'error_code': 4
        },
    }
    SUCCESS_MESSAGES = {
        'socket_opened': {
            'message': 'Соединение установлено'
        }
    }
    
    async def remove_websocket(self, user_id: int = None):
        if not user_id:
            self.request.app['ws_connections'].pop(user_id)
        else:
            await self.remove_closed_websockets()
        await self.web_socket_request.close()
        
    async def add_websocket_to_list(self, user_id):
        self.request.app['ws_connections'][user_id] = self.web_socket_request

    async def remove_closed_websockets(self):
        user_ids_to_delete = []
        for user_id, ws_n in self.request.app['ws_connections'].items():
            if ws_n.closed() or self.web_socket_request == ws_n:
                user_ids_to_delete.append(user_id)
        for user_id in user_ids_to_delete:
            self.request.app['ws_connections'].pop(user_id)
        
    async def dispatch(self, request):
        self.web_socket_request = web.WebSocketResponse()
        self.request = request
        await self.web_socket_request.prepare(request)

        msg: WSMessage
        async for msg in self.web_socket_request:
            await self.remove_closed_websockets()
            try:
                await self.websocket_handler(msg)
            except Exception as e:
                LOG.exception(e)
        return self.web_socket_request

    async def send_answer(self, answer: WebSocketResponseType, web_socket=None):
        web_socket = web_socket or self.web_socket_request
        await web_socket.send_json(answer.to_dict())
        return web_socket

    async def check_token(self, connection, data):
        tokens = await ChatToken.manager.all(connection)
        if not check_valid_token(tokens, data.token):
            answer = WebSocketResponseType(
                status='FAIL',
                graph=None,
                message=self.ERROR_MESSAGES['invalid_token']['message'],
                error_code=self.ERROR_MESSAGES['invalid_token']['error_code'],
            )
            await self.remove_websocket()
            return self.send_answer(answer)

    async def send_by_graph_members(self, connection, graph: Graph):
        members = await get_user_command_members(connection, graph.user_id)
        for member in members:
            web_socket = self.request.app['ws_connections'].get(member)
            if web_socket:
                answer = WebSocketResponseType(
                    status='OK',
                    graph=GraphType(graph.id, graph.content),
                )
                await self.send_answer(answer, web_socket)
    
    async def websocket_handler(self, msg: WSMessage):
        try:
            async with self.request.app['pool'].acquire() as connection:
                if msg.type == WSMsgType.TEXT:
                    data = WebSocketRequestType(**msg.json())
                    if data.action == 'CLOSE':
                        await self.remove_websocket()
                    elif data.action == 'OPEN':
                        await self.check_token(connection, data)
                        await self.add_websocket_to_list(data.user_id)
                        answer = WebSocketResponseType(
                            status='OK',
                            graph=None,
                            message=self.SUCCESS_MESSAGES['socket_opened']['message'],
                        )
                        return self.send_answer(answer)

                    elif data.action == 'UPDATE':
                        await self.check_token(connection, data)
                        try:
                            await self.check_token(connection, data)
                            graph = await Graph().manager.filter(connection, action='WHERE', id=data.graph.id)
                            graph = graph[0]
                            if graph.user_id == data.user_id:
                                graph.content = data.graph.content
                                graph.save(connection)
                                answer = WebSocketResponseType(
                                    status='OK',
                                    graph=GraphType(graph.id, graph.content),
                                )
                                await self.send_by_graph_members(connection, graph.user_id)
                                return self.send_answer(answer)
                            else:
                                raise ProcessGraphException(**self.ERROR_MESSAGES['graph_forbidden'])
                        except IndexError as e:
                            LOG.exception(e)
                            raise ProcessGraphException(**self.ERROR_MESSAGES['graph_not_found'])

                    else:
                        if data.graph and data.graph.id:
                            try:
                                await self.check_token(connection, data)
                                graph = await Graph().manager.filter(connection, action='WHERE', id=data.graph.id)
                                graph = graph[0]
                                answer = WebSocketResponseType(
                                    status='OK',
                                    graph=GraphType(graph.id, graph.content),
                                )
                                return self.send_answer(answer)
                            except IndexError as e:
                                LOG.exception(e)
                                raise ProcessGraphException(**self.ERROR_MESSAGES['graph_forbidden'])
                        else:
                            raise ProcessGraphException(**self.ERROR_MESSAGES['invalid_type'])

                elif msg.type == WSMsgType.ERROR:
                    LOG.error('ws connection closed with exception %s' %
                              self.web_socket_request.exception())
        except ProcessGraphException as e:
            answer = WebSocketResponseType(
                status='FAIL',
                graph=None,
                message=e.message,
                error_code=e.error_code,
            )
            return self.send_answer(answer)
        return self.web_socket_request
