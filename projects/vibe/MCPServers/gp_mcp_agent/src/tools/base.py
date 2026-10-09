"""Базовый класс MCP tool."""

from abc import ABC, abstractmethod


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self):
        # type: () -> str
        pass

    @property
    @abstractmethod
    def description(self):
        # type: () -> str
        pass

    @abstractmethod
    def input_schema(self):
        # type: () -> dict
        pass

    @abstractmethod
    def execute(self, arguments):
        # type: (dict) -> object
        pass

    def schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema(),
        }
