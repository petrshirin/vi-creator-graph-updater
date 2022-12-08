import typing

from src.models import ChatToken, GraphType, WebSocketRequestType, Graph


def check_valid_token(tokens: typing.List[ChatToken], token_for_check: str):
    for token in tokens:
        if token.token == token_for_check:
            return token


def validate_request_data(data: dict, schema):
    data = WebSocketRequestType(**data)
    assert type(data.token) != str, TypeError('token должен быть str типа')
    assert type(data.user_id) != int, TypeError('user_id должен быть int типа')
    assert type(data.graph) != GraphType, TypeError('graph должен быть содержать id и content типа')
