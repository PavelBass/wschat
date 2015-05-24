import hashlib
import collections
import json

from abc import ABCMeta, abstractmethod, abstractproperty

try:
    import redis
except ImportError:
    redis = None


UserRecord = collections.namedtuple('UserRecord', "pass_hash allowed_rooms current_rooms")


class DB(object):
    __metaclass__ = ABCMeta

    _default_rooms = ('Free Chat', 'Python Developers', 'JavaScript Developers')
    _default_room = _default_rooms[0]

    @abstractmethod
    def is_correct_user(self, login, password):
        """ Check if passed login is in base and password is correct

        :param login: passed login
        :param password: passed password (not hash)
        :return:
            None: if login not in database
            True: if login in database and password is correct
            False: if login in database but password is not correct
        """
        pass

    @abstractmethod
    def get_current_rooms(self, login):
        """ Return current rooms of user
        :param login: user login
        :return: list/tuple of current rooms
        """
        pass

    @abstractmethod
    def add_room_to_current(self, login, room):
        """ Add room to current rooms for user
            and rewrite his record in DataBase
        :param login: user login
        :param room: new room
        """
        pass

    @abstractmethod
    def remove_room_from_current(self, login, room):
        """ Remove room from current rooms for user
             and rewrite his record in DataBase
        :param login: user login
        :param room: room name to remove
        """
        pass

    @abstractmethod
    def get_room_history(self, room):
        """ Return room history (if room exists)

        :param room: room name
        :return:
            None: if room doesn't exists
            list: last 10 messages in room
        """
        pass

    @abstractmethod
    def change_nick_in_room(self, login, room, nick):
        """ Change nick of user with received login in room
        :param login: user login
        :param room: room name
        :param nick: new nick
        """
        pass

    @abstractmethod
    def get_current_nick(self, login, room):
        """ Return stored nickname of user for room
        :param login: user login
        :param room: room name
        :return: nickname
        """
        pass

    @abstractmethod
    def new_user(self, login, password):
        """ Create new user
        :param login: passed login
        :param password: passed password
        :return:
            None: if user already exists
            list: default allowed rooms
        """
        pass

    @abstractmethod
    def new_room(self, room):
        """ Create new room
        :param room: room name
        :return:
            False: if such room already exists
            True: after creation
        """
        pass

    @abstractmethod
    def new_message(self, room, mess):
        """ Save new message into room history
        :param room: room name
        :param mess: message
        :return: None
        """
        pass

    @abstractproperty
    def all_rooms(self):
        """ Return all existent rooms
        :return: list/tuple of rooms
        """
        pass

    @property
    def default_room(self):
        return self._default_room

    @property
    def default_rooms(self):
        return self._default_rooms


class DBPython(DB):
    def __init__(self):
        self._users = dict()
        self._rooms = dict()
        for room in self.default_rooms:
            self._rooms[room] = list()

    def is_correct_user(self, login, password):
        user = self._users.get(login, None)
        if user is None:
            return
        return hashlib.md5(password).hexdigest() == user.pass_hash

    def get_current_rooms(self, login):
        rooms = (self.default_room,)
        if login in self._users:
            rooms = self._users[login].current_rooms
            rooms = (x[0] for x in rooms)
        return rooms

    def add_room_to_current(self, login, room):
        if login is None or room in self.get_current_rooms(login):
            return
        user = self._users[login]
        rooms = list(user.current_rooms)
        rooms.append((room, login,))
        self._users[login] = UserRecord(user.pass_hash, user.allowed_rooms, tuple(rooms))

    def remove_room_from_current(self, login, room):
        user = self._users[login]
        rooms = list(user.current_rooms)
        for n, _room in enumerate(rooms[:]):
            if room == _room[0]:
                rooms.pop(n)
                break
        self._users[login] = UserRecord(user.pass_hash, user.allowed_rooms, tuple(rooms))

    def get_room_history(self, room):
        history = self._rooms.get(room, None)
        if history is not None:
            history = history[-10:]
        return history

    def change_nick_in_room(self, login, room, nick):
        if login is None:
            return
        user = self._users[login]
        rooms = list(user.current_rooms)
        for _room in rooms[:]:
            if room == _room[0]:
                rooms[rooms.index(_room)] = (room, nick,)
        self._users[login] = UserRecord(user.pass_hash, user.allowed_rooms, tuple(rooms))

    def get_current_nick(self, login, room):
        if login is None:
            return 'Anonymous'
        user = self._users[login]
        rooms = list(user.current_rooms)
        for _room in rooms[:]:
            if room == _room[0]:
                return _room[1]

    def new_user(self, login, password):
        if login in self._users:
            return
        allowed_rooms = (self.default_room,)
        self._users[login] = UserRecord(hashlib.md5(password).hexdigest(), allowed_rooms, tuple())
        return allowed_rooms

    def new_room(self, room):
        if room in self._rooms:
            return False
        self._rooms[room] = list()
        return True

    def new_message(self, room, mess):
        self._rooms[room].append(mess)

    @property
    def all_rooms(self):
        return self._rooms.keys()


class DBRedis(DB):
    def __init__(self):
        self.r = redis.Redis()
        self._pre = 'RamblerTaskChat:'
        for room in self.default_rooms:
            key = '%sROOM:%s' % (self._pre, room)
            if not self.r.exists(key):
                self.r.lpush(key, 'Created room "%s"' % room)


    def is_correct_user(self, login, password):
        key = '%sUSER:%s' % (self.pre, login)
        pass_hash = self.r.hget(key, 'pass_hash')
        if pass_hash is None:
            return
        return hashlib.md5(password).hexdigest() == pass_hash

    def get_current_rooms(self, login):
        key = '%sUSER:%s' % (self.pre, login)
        rooms = self.r.hget(key, 'current_rooms')
        rooms = json.loads(rooms)
        return (x[0] for x in rooms)

    def add_room_to_current(self, login, room):
        if login is None or room in self.get_current_rooms(login):
            return
        key = '%sUSER:%s' % (self.pre, login)
        rooms = self.r.hget(key, 'current_rooms')
        rooms = json.loads(rooms)
        rooms.append((room, login,))
        self.r.hset(key, 'current_rooms', json.dumps(rooms))

    def remove_room_from_current(self, login, room):
        key = '%sUSER:%s' % (self.pre, login)
        rooms = self.r.hget(key, 'current_rooms')
        rooms = json.loads(rooms)
        for n, _room in enumerate(rooms[:]):
            if room == _room[0]:
                rooms.pop(n)
                break
        self.r.hset(key, 'current_rooms', json.dumps(rooms))

    def get_room_history(self, room):
        key = '%sROOM:%s' % (self._pre, room)
        return self.r.lrange(key, -10, -1)

    def change_nick_in_room(self, login, room, nick):
        key = '%sUSER:%s' % (self.pre, login)
        rooms = self.r.hget(key, 'current_rooms')
        rooms = json.loads(rooms)
        for _room in rooms[:]:
            if room == _room[0]:
                rooms[rooms.index(_room)] = (room, nick,)
        self.r.hset(key, 'current_rooms', json.dumps(rooms))

    def get_current_nick(self, login, room):
        if login is None:
            return 'Anonymous'
        key = '%sUSER:%s' % (self.pre, login)
        rooms = self.r.hget(key, 'current_rooms')
        rooms = json.loads(rooms)
        for _room in rooms[:]:
            if room == _room[0]:
                return _room[1]

    def new_user(self, login, password):
        key = '%sUSER:%s' % (self.pre, login)
        if self.r.exists(key):
            return
        allowed_rooms = [self.default_room]
        vals = dict(
            pass_hash=hashlib.md5(password).hexdigest(),
            allowed_rooms=json.dumps(allowed_rooms),
            current_rooms='[]'
        )
        self.r.hmset(key, vals)
        return allowed_rooms

    def new_room(self, room):
        key = '%sROOM:%s' % (self._pre, room)
        if self.r.exists(key):
            return False
        return True

    def new_message(self, room, mess):
        key = '%sROOM:%s' % (self._pre, room)
        self.r.rpush(key, mess)

    @property
    def all_rooms(self):
        key = '%sROOM:*' % self._pre
        rooms = self.r.keys(key)
        l = len(key) - 1
        return [x[l:] for x in rooms]

    @property
    def pre(self):
        return self._pre

