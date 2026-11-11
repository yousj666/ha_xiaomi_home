"""Conversation agent for Xiaomi Home (Lite-Safety BYOK AI assistant).

Registers a Home Assistant conversation agent backed by the
user-configured LLM endpoint (see lite_safety.async_ask_ai). The agent
answers questions about the home and, when the user clearly asks for
it, executes one allow-listed service call.
"""
from __future__ import annotations

import logging

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .lite_safety import async_ask_ai

_LOGGER = logging.getLogger(__name__)


async def async_get_agent(
    hass: HomeAssistant, entry: ConfigEntry
) -> 'LiteSafetyConversationAgent':
    """Return the Lite-Safety conversation agent for an entry."""
    return LiteSafetyConversationAgent(entry)


class LiteSafetyConversationAgent(conversation.AbstractConversationAgent):
    """Conversation agent that forwards to the BYOK LLM endpoint."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the agent."""
        self._entry = entry

    @property
    def supported_languages(self) -> str:
        """Return supported languages (all)."""
        return '*'

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a user utterance with the configured LLM."""
        response = intent.IntentResponse(language=user_input.language)
        try:
            text = await async_ask_ai(
                self.hass, user_input.text, allow_control=True)
        except ValueError as err:
            text = str(err)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error('Lite-Safety AI agent error, %s', err)
            text = 'AI assistant error, please check the logs.'
        response.async_set_speech(text)
        return conversation.ConversationResult(
            response=response, conversation_id=user_input.conversation_id)
