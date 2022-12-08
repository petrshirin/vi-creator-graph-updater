import dataclasses
from dataclasses import dataclass
from asyncpg.connection import Connection
import typing


class Manager:

    def __init__(self, table: str, model):
        self.table = table
        self.model = model

    def first(self, conn: Connection):
        return self.all(conn)[0] if self.all(conn) else None

    def _create_sql(self, action=None, **kwargs):
        base_sql = f'SELECT * FROM {self.table}'
        if not kwargs:
            return base_sql
        else:
            if action == 'WHERE':
                base_sql = ' WHERE '

        for field in kwargs.keys():
            if 'AND' not in base_sql:
                base_sql += f' AND {field}={kwargs[field]} '
        return base_sql

    def _to_objects(self, rows) -> list:
        objects = []
        for row in rows:
            new_token = self.model(**row)
            objects.append(new_token)
        return objects

    async def filter(self, conn: Connection, **kwargs) -> list:
        rows = await conn.fetch(self._create_sql(**kwargs))
        return self._to_objects(rows)

    async def all(self, conn: Connection) -> list:
        rows = await conn.fetch(self._create_sql())
        return self._to_objects(rows)

    def get_sql_for_update_fields(self, model):
        return ','.join([f'{key}={getattr(model, key)}' for key in model.fields])

    async def save(self, conn, instance: 'Model'):
        sql_row = f'UPDATE FROM {self.table} SET {self.get_sql_for_update_fields(instance)} WHERE id={instance.id}'
        return await conn.fetch(sql_row)


class Model:
    base_fields = ('id', )
    id: int
    fields: tuple
    table: str
    manager: Manager

    def __init__(self, **kwargs):
        self.manager = Manager(self.table, self.__class__)
        for field in self.base_fields + self.fields:
            setattr(self, field, kwargs.get(field))

    async def save(self, conn):
        return await self.manager.save(conn, self)


class ChatToken(Model):
    user_id = None
    token = None

    table = 'authtoken_token'
    fields = ('user_id', 'token')


class Graph(Model):
    user_id = None
    content = None
    is_active = None
    mark = None

    table = 'graphconstructor_usergraphconstructor'
    fields = ('user_id', 'content', 'is_active', 'mark')


async def check_graph_permission(connection: Connection, user_id: int, graph_id: int):
    sql = f'SELECT * FROM core_user where user_id={user_id} LIMIT 1'
    rows = await connection.fetch(sql)
    # TODO: логика проверки графа


async def get_user_command_members(connection, user_id) -> list[int]:
    sql = f'SELECT (teacher_id) FROM core_user WHERE id=user_id LIMIT 1'
    row = await connection.fetch(sql)
    if row:
        sql = f'SELECT (user_id) FROM core_teacher_student_group WHERE teacher_id={row["teacher_id"]}'
        rows = await connection.fetch(sql)
        return list(map(lambda r: int(r['user_id']), rows))
    return []

@dataclass
class GraphType:
    id: int = 0
    content: str = ""

    def to_dict(self):
        return {'id': self.id, 'content': self.content}


@dataclass
class WebSocketRequestType:
    token: typing.AnyStr
    action: typing.Literal['OPEN', 'CLOSE', 'UPDATE', 'GET']
    user_id: int
    graph: typing.Union[dict, GraphType] = dataclasses.field(default_factory=GraphType)

    def __post_init__(self):
        if self.graph and not isinstance(self.graph, dict):
            self.graph = GraphType(**self.graph)
        if not self.graph:
            self.graph = GraphType()


@dataclass
class WebSocketResponseType:
    status: typing.Literal['OK', 'FAIL']
    graph: dataclasses.field(init=False)
    message: str = None
    error_code: typing.Union[int, None] = None

    def to_dict(self):
        data = {'status': self.status, 'graph': self.graph.to_dict()}
        if self.message:
            data['message'] = self.message
        if self.error_code:
            data['error_code'] = self.error_code

        return data
