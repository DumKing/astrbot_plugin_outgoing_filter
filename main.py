from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star

from .rules import compile_rule


class OutgoingFilter(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.rules = []
        self.debug_logs = config.get("debug_logs", False)
        if config.get("enabled", True):
            for index, raw in enumerate(config.get("rules", []), 1):
                if not raw.get("enabled", True):
                    continue
                try:
                    rule = compile_rule(raw)
                    label = f"#{index} [{raw['__template_key']}] {raw.get('name', '')}".strip()
                    self.rules.append((label, rule))
                except (ValueError, KeyError, TypeError) as exc:
                    logger.warning(f"[出站文本过滤] 第 {index} 条规则无效，已跳过 ({type(exc).__name__})")

        if self.debug_logs:
            logger.info(f"[出站文本过滤] 已加载 {len(self.rules)} 条有效规则")

    @filter.on_decorating_result()
    async def filter_outgoing(self, event: AstrMessageEvent):
        result = event.get_result()
        if not self.rules or not result or not result.chain:
            return
        texts = [(index, item.text) for index, item in enumerate(result.chain) if isinstance(item, Plain)]
        if not texts:
            return

        changed = False
        umo = event.unified_msg_origin
        for label, rule in self.rules:
            if reason := rule.skip_reason(umo):
                if self.debug_logs:
                    logger.info(f"[出站文本过滤] {umo} {label} 跳过：{reason}")
                continue
            updated = []
            matches = 0
            for index, text in texts:
                if text:
                    new_text, count = rule.replace(text)
                    matches += count
                    changed |= new_text != text
                    text = new_text
                updated.append((index, text))
            texts = updated
            stop = bool(matches and rule.stop)
            if self.debug_logs:
                suffix = "，停止后续规则" if stop else ""
                logger.info(f"[出站文本过滤] {umo} {label} 命中 {matches} 处{suffix}")
            if stop:
                break

        if changed:
            for index, text in reversed(texts):
                if text != result.chain[index].text:
                    if text:
                        result.chain[index].text = text
                    else:
                        del result.chain[index]
