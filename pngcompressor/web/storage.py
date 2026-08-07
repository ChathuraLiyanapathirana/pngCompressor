"""Processed-result storage."""

import secrets
from abc import ABC, abstractmethod
from collections import OrderedDict


class ResultStore(ABC):
    @abstractmethod
    def put(self, filename, data):
        raise NotImplementedError

    @abstractmethod
    def get_many(self, tokens):
        raise NotImplementedError


class MemoryResultStore(ResultStore):
    def __init__(self, max_entries=200):
        self._entries = OrderedDict()
        self._max = max_entries

    def put(self, filename, data):
        token = secrets.token_urlsafe(12)
        self._entries[token] = (filename, data)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)
        return token

    def get_many(self, tokens):
        return [self._entries[t] for t in tokens if t in self._entries]
