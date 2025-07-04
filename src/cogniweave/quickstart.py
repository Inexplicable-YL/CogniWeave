from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.prompts import MessagesPlaceholder

from cogniweave.core.end_detector import EndDetector
from cogniweave.core.history_stores import BaseHistoryStore as HistoryStore
from cogniweave.core.time_splitter import TimeSplitter
from cogniweave.core.vector_stores import TagsVectorStore
from cogniweave.llms import AgentBase, OpenAIEmbeddings, StringSingleTurnChat
from cogniweave.prompt_values import MultilingualStringPromptValue
from cogniweave.prompts import MessageSegmentsPlaceholder, RichSystemMessagePromptTemplate
from cogniweave.runnables.end_detector import RunnableWithEndDetector
from cogniweave.runnables.history_store import RunnableWithHistoryStore
from cogniweave.runnables.memory_maker import RunnableWithMemoryMaker
from cogniweave.utils import get_model_from_env, get_provider_from_env

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

DEF_FOLDER_PATH = Path("./.cache/")


def create_embeddings(
    provider: str | None = None,
    model: str | None = None,
) -> OpenAIEmbeddings:
    """Create default embeddings instance."""
    return OpenAIEmbeddings(
        provider=get_provider_from_env("EMBEDDINGS_MODEL", default=provider or "openai")(),
        model=get_model_from_env("EMBEDDINGS_MODEL", default=model or "text-embedding-ada-002")(),
    )


def create_history_store(
    *, index_name: str = "demo", folder_path: str | Path = DEF_FOLDER_PATH
) -> HistoryStore:
    """Create a history store backed by a SQLite database."""
    return HistoryStore(db_url=f"sqlite:///{folder_path}/{index_name}.sqlite")


def create_vector_store(
    embeddings: OpenAIEmbeddings,
    *,
    index_name: str = "demo",
    folder_path: str | Path = DEF_FOLDER_PATH,
) -> TagsVectorStore:
    """Create a vector store for long term memory."""
    return TagsVectorStore(
        folder_path=str(folder_path),
        index_name=index_name,
        embeddings=embeddings,
        allow_dangerous_deserialization=True,
        auto_save=True,
    )


def create_chat(
    lang: str | None = None,
    *,
    prompt: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> StringSingleTurnChat:
    """Create the base chat agent."""
    lang = lang or os.getenv("LANGUAGE", "zh")
    prompt_list = [
        *([prompt] if prompt else MultilingualStringPromptValue().to_messages(lang=lang)),
        "\n",
    ]
    return StringSingleTurnChat(
        lang=lang,
        provider=get_provider_from_env("CHAT_MODEL", default=provider or "openai")(),
        model=get_model_from_env("CHAT_MODEL", default=model or "gpt-4.1")(),
        contexts=[
            RichSystemMessagePromptTemplate.from_template(
                [
                    *prompt_list,
                    MessageSegmentsPlaceholder(variable_name="long_memory"),
                ]
            ),
            MessagesPlaceholder(variable_name="history", optional=True),
        ],
    )


def create_agent(
    lang: str | None = None,
    *,
    prompt: str | None = None,
    tools: list[BaseTool] | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> AgentBase:
    """Create the base chat agent."""
    lang = lang or os.getenv("LANGUAGE", "zh")
    prompt_list = [
        *([prompt] if prompt else MultilingualStringPromptValue().to_messages(lang=lang)),
        "\n",
    ]
    return AgentBase(
        lang=lang,
        provider=get_provider_from_env("AGENT_MODEL", default=provider or "openai")(),
        model=get_model_from_env("AGENT_MODEL", default=model or "gpt-4.1")(),
        contexts=[
            RichSystemMessagePromptTemplate.from_template(
                [
                    *prompt_list,
                    MessageSegmentsPlaceholder(variable_name="long_memory"),
                ]
            ),
            MessagesPlaceholder(variable_name="history", optional=True),
        ],
        tools=tools or [],
    )


def build_pipeline(
    lang: str | None = None,
    prompt: str | None = None,
    *,
    index_name: str = "demo",
    folder_path: str | Path = DEF_FOLDER_PATH,
) -> RunnableWithHistoryStore:
    """Assemble the runnable pipeline used in the demos."""
    embeddings = create_embeddings()
    history_store = create_history_store(index_name=index_name, folder_path=folder_path)
    vector_store = create_vector_store(embeddings, index_name=index_name, folder_path=folder_path)
    agent = create_chat(lang=lang, prompt=prompt)

    pipeline = RunnableWithMemoryMaker(
        agent,
        history_store=history_store,
        vector_store=vector_store,
        input_messages_key="input",
        history_messages_key="history",
        short_memory_key="short_memory",
        long_memory_key="long_memory",
    )
    pipeline = RunnableWithEndDetector(
        pipeline,
        end_detector=EndDetector(),
        default={"output": []},
        history_messages_key="history",
    )
    return RunnableWithHistoryStore(
        pipeline,
        history_store=history_store,
        time_splitter=TimeSplitter(),
        input_messages_key="input",
        history_messages_key="history",
    )
