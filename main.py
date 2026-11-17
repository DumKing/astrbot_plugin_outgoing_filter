from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star

from .rules import compile_rule


class OutgoingFilter(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.rules = []
        if config.get("enabled", True):
            for index, raw in enumerate(config.get("rules", []), 1):
                if not raw.get("enabled", True):
                    continue
                try:
                    self.rules.append(compile_rule(raw))
                except (ValueError, KeyError, TypeError) as exc:
                    logger.warning("出站文本过滤第 %s 条规则无效，已跳过 (%s)", index, type(exc).__name__)

    @filter.on_decorating_result()
    async def filter_outgoing(self, event: AstrMessageEvent):
        result = event.get_result()
        if not self.rules or not result or not result.chain:
            return
        texts = [(index, item.text) for index, item in enumerate(result.chain) if isinstance(item, Plain)]
        if not texts:
            return

        changed = False
        for rule in self.rules:
            if not rule.applies(event.unified_msg_origin):
                continue
            updated = []
            matched = False
            for index, text in texts:
                if text:
                    new_text, count = rule.replace(text)
                    matched |= bool(count)
                    changed |= new_text != text
                    text = new_text
                updated.append((index, text))
            texts = updated
            if matched and rule.stop:
                break

        if changed:
            for index, text in reversed(texts):
                if text.strip():
                    result.chain[index].text = text
                else:
                    del result.chain[index]
