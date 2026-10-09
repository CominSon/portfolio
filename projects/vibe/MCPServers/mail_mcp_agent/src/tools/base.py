"""Базовый класс MCP tool."""

from abc import ABC, abstractmethod


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self):
        pass

    @property
    @abstractmethod
    def description(self):
        pass

    @abstractmethod
    def input_schema(self):
        pass

    @abstractmethod
    def execute(self, arguments):
        pass

    def schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema(),
        }
