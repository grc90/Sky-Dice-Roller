"""
Tests for core dice logic — no Telegram API required.

Run with:  python -m pytest tests/ -v
           (from the project root, with venv active)
"""
import asyncio
import json
import os
import sys
import types
import random
import pathlib
import importlib.util
from collections import deque
from datetime import datetime, timedelta

import pytest

# ── Stub all external dependencies before importing bot ──────────────────────

for mod_name in ["telegram", "telegram.ext", "telegram.error", "dotenv"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

class _Stub:
    """Generic stub that records its constructor args so tests can inspect them."""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)

_tg = sys.modules["telegram"]
for _attr in [
    "Update", "InlineQueryResultArticle", "InputTextMessageContent",
    "InlineKeyboardButton", "InlineKeyboardMarkup",
]:
    setattr(_tg, _attr, _Stub)

class _TelegramError(Exception):
    pass

sys.modules["telegram.error"].TelegramError = _TelegramError

_ext = sys.modules["telegram.ext"]
for _cls in [
    "Application", "CommandHandler", "InlineQueryHandler",
    "CallbackQueryHandler", "ContextTypes",
]:
    setattr(_ext, _cls, object)

sys.modules["dotenv"].load_dotenv = lambda: None
os.environ.setdefault("BOT_TOKEN", "stub-token-for-tests")

# ── Load bot module ───────────────────────────────────────────────────────────

_bot_path = str(pathlib.Path(__file__).parent.parent / "bot.py")
_spec = importlib.util.spec_from_file_location("bot", _bot_path)
bot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bot)


# ── parse_roll ────────────────────────────────────────────────────────────────

class TestParseRoll:
    def test_basic(self):
        s = bot.parse_roll("3d6")
        assert s.num_dice == 3
        assert s.sides == 6
        assert s.sel_mode is None
        assert s.modifier == 0

    def test_default_one_die(self):
        s = bot.parse_roll("d20")
        assert s.num_dice == 1
        assert s.sides == 20

    def test_modifier_positive(self):
        assert bot.parse_roll("2d8+3").modifier == 3

    def test_modifier_negative(self):
        assert bot.parse_roll("1d6-1").modifier == -1

    def test_keep_highest(self):
        s = bot.parse_roll("4d6kh3")
        assert s.sel_mode == "kh" and s.sel_n == 3

    def test_keep_lowest(self):
        s = bot.parse_roll("5d10kl2")
        assert s.sel_mode == "kl" and s.sel_n == 2

    def test_drop_highest(self):
        s = bot.parse_roll("6d8dh2")
        assert s.sel_mode == "dh" and s.sel_n == 2

    def test_drop_lowest(self):
        s = bot.parse_roll("4d6dl1")
        assert s.sel_mode == "dl" and s.sel_n == 1

    def test_combined_selector_and_modifier(self):
        s = bot.parse_roll("4d6kh3+2")
        assert s.sel_mode == "kh" and s.sel_n == 3 and s.modifier == 2

    def test_case_insensitive(self):
        s = bot.parse_roll("3D6KH2")
        assert s.sel_mode == "kh" and s.sides == 6

    def test_normalized_expr(self):
        assert bot.parse_roll("3D6").expr == "3d6"

    def test_normalized_expr_with_modifier(self):
        assert bot.parse_roll("2d20+5").expr == "2d20+5"

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            bot.parse_roll("abc")

    def test_zero_dice(self):
        with pytest.raises(ValueError):
            bot.parse_roll("0d6")

    def test_too_many_dice(self):
        with pytest.raises(ValueError):
            bot.parse_roll(f"{bot.MAX_DICE + 1}d6")

    def test_one_side(self):
        with pytest.raises(ValueError):
            bot.parse_roll("1d1")

    def test_selector_equal_to_dice(self):
        with pytest.raises(ValueError):
            bot.parse_roll("3d6kh3")

    def test_selector_exceeds_dice(self):
        with pytest.raises(ValueError):
            bot.parse_roll("2d6kh3")

    def test_backtick_in_input_sanitized(self):
        # Backticks in the user input must not break the ValueError Markdown
        try:
            bot.parse_roll("`bad`")
        except ValueError as e:
            assert "`bad`" not in str(e)   # raw backtick escaped
            assert "'" in str(e)           # replaced with single quote

    def test_empty_string(self):
        with pytest.raises(ValueError):
            bot.parse_roll("")


# ── execute_roll ──────────────────────────────────────────────────────────────

class TestExecuteRoll:
    def test_result_in_range(self):
        spec = bot.parse_roll("3d6")
        result = bot.execute_roll(spec)
        assert 3 <= result.total <= 18
        assert len(result.all_rolls) == 3
        assert result.dropped == []

    def test_subtotal_plus_modifier(self):
        random.seed(42)
        spec = bot.parse_roll("2d6+3")
        result = bot.execute_roll(spec)
        assert result.total == result.subtotal + 3
        assert result.subtotal == sum(result.all_rolls)

    def test_keep_highest_keeps_correct(self):
        spec = bot.parse_roll("4d6kh3")
        result = bot.execute_roll(spec)
        assert len(result.kept) == 3
        assert len(result.dropped) == 1
        assert min(result.kept) >= result.dropped[0]

    def test_keep_lowest_keeps_correct(self):
        spec = bot.parse_roll("4d6kl2")
        result = bot.execute_roll(spec)
        assert len(result.kept) == 2
        assert max(result.kept) <= min(result.dropped)

    def test_drop_highest_drops_correct(self):
        spec = bot.parse_roll("4d6dh1")
        result = bot.execute_roll(spec)
        assert len(result.kept) == 3
        assert result.dropped[0] >= max(result.kept)

    def test_drop_lowest_drops_correct(self):
        spec = bot.parse_roll("4d6dl1")
        result = bot.execute_roll(spec)
        assert len(result.kept) == 3
        assert result.dropped[0] <= min(result.kept)

    def test_subtotal_is_sum_of_kept(self):
        spec = bot.parse_roll("5d10kh3")
        result = bot.execute_roll(spec)
        assert result.subtotal == sum(result.kept)
        assert result.total == result.subtotal + spec.modifier


# ── parse_stats_variant ───────────────────────────────────────────────────────

class TestParseStatsVariant:
    def test_default_is_standard(self):
        assert bot.parse_stats_variant(None).expr == "4d6dl1"

    def test_standard(self):
        assert bot.parse_stats_variant("standard").expr == "4d6dl1"

    def test_dnd_alias(self):
        assert bot.parse_stats_variant("dnd").expr == "4d6dl1"

    def test_classic(self):
        assert bot.parse_stats_variant("classic").expr == "3d6"

    def test_heroic(self):
        assert bot.parse_stats_variant("heroic").expr == "5d6dl2"

    def test_grim(self):
        assert bot.parse_stats_variant("grim").expr == "3d6kl2"

    def test_custom_expression(self):
        assert bot.parse_stats_variant("4d6kh3").expr == "4d6kh3"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            bot.parse_stats_variant("xyz_invalid_99")

    def test_case_insensitive(self):
        assert bot.parse_stats_variant("STANDARD").expr == "4d6dl1"


# ── format_result ─────────────────────────────────────────────────────────────

class TestFormatResult:
    def test_single_die_no_modifier_omits_total(self):
        spec = bot.parse_roll("1d20")
        result = bot.execute_roll(spec)
        text = bot.format_result(spec, result)
        assert "1d20" in text
        assert "Total" not in text        # redundant line removed
        assert "Resultado" in text

    def test_single_die_with_modifier_shows_total(self):
        spec = bot.parse_roll("1d6+3")
        result = bot.execute_roll(spec)
        text = bot.format_result(spec, result)
        assert "Total" in text
        assert "+ 3" in text

    def test_multiple_dice_shows_total(self):
        spec = bot.parse_roll("3d6")
        result = bot.execute_roll(spec)
        assert "Total" in bot.format_result(spec, result)

    def test_nat20_annotation(self):
        spec = bot.parse_roll("1d20")
        # Force a max roll
        result = bot.RollResult([20], [20], [], 20, 20)
        text = bot.format_result(spec, result)
        assert "Crítico" in text

    def test_pifia_annotation(self):
        spec = bot.parse_roll("1d20")
        result = bot.RollResult([1], [1], [], 1, 1)
        text = bot.format_result(spec, result)
        assert "Pifia" in text

    def test_no_annotation_for_multi_dice(self):
        spec = bot.parse_roll("2d20")
        result = bot.execute_roll(spec)
        text = bot.format_result(spec, result)
        assert "Crítico" not in text
        assert "Pifia" not in text


# ── Message length safety ─────────────────────────────────────────────────────

class TestMessageLength:
    def test_max_dice_no_selector(self):
        spec = bot.parse_roll(f"{bot.MAX_DICE}d6")
        result = bot.execute_roll(spec)
        text = bot.format_result(spec, result)
        assert len(text) <= bot.MAX_MSG_LEN

    def test_max_dice_with_selector(self):
        spec = bot.parse_roll(f"{bot.MAX_DICE}d6kh3")
        result = bot.execute_roll(spec)
        text = bot.format_result(spec, result)
        assert len(text) <= bot.MAX_MSG_LEN

    def test_stats_worst_case(self):
        spec = bot.parse_roll(f"{bot.MAX_DICE}d6kh3")
        rolls = [bot.execute_roll(spec) for _ in range(bot.STATS_ROLLS)]
        text = bot.format_stats(spec, rolls)
        assert len(text) <= bot.MAX_MSG_LEN

    def test_truncate_dice_list_short(self):
        rolls = list(range(1, 6))
        result = bot._truncate_dice_list(rolls)
        assert "…" not in result
        assert "1" in result

    def test_truncate_dice_list_long(self):
        rolls = [3] * (bot.MAX_DISPLAY_DICE + 5)
        result = bot._truncate_dice_list(rolls)
        assert "…" in result
        assert "+5 más" in result


# ── Roll annotation ───────────────────────────────────────────────────────────

class TestRollAnnotation:
    def test_nat20_on_d20(self):
        spec = bot.parse_roll("1d20")
        result = bot.RollResult([20], [20], [], 20, 20)
        assert "Crítico" in bot._roll_annotation(spec, result)

    def test_pifia_on_d20(self):
        spec = bot.parse_roll("1d20")
        result = bot.RollResult([1], [1], [], 1, 1)
        assert "Pifia" in bot._roll_annotation(spec, result)

    def test_no_annotation_with_modifier(self):
        spec = bot.parse_roll("1d20+5")
        result = bot.RollResult([20], [20], [], 20, 25)
        assert bot._roll_annotation(spec, result) == ""

    def test_no_annotation_multi_dice(self):
        spec = bot.parse_roll("2d6")
        result = bot.execute_roll(spec)
        assert bot._roll_annotation(spec, result) == ""

    def test_crit_on_any_die_type(self):
        spec = bot.parse_roll("1d6")
        result = bot.RollResult([6], [6], [], 6, 6)
        assert "Crítico" in bot._roll_annotation(spec, result)


# ── LRU user history ──────────────────────────────────────────────────────────

class TestLRUHistory:
    def setup_method(self):
        """Reset shared user_history before every test."""
        bot.user_history.clear()

    def test_creates_deque_for_new_user(self):
        h = bot._get_history(1)
        assert isinstance(h, deque)
        assert h.maxlen == bot.HISTORY_MAXLEN

    def test_same_deque_returned_on_repeated_access(self):
        h1 = bot._get_history(42)
        h1.append("roll1")
        h2 = bot._get_history(42)
        assert h2 is h1
        assert "roll1" in h2

    def test_deque_respects_maxlen(self):
        h = bot._get_history(1)
        for i in range(bot.HISTORY_MAXLEN + 5):
            h.append(f"roll{i}")
        assert len(h) == bot.HISTORY_MAXLEN

    def test_evicts_oldest_user_when_over_limit(self):
        limit = bot.MAX_HISTORY_USERS
        # Fill to the limit
        for uid in range(limit):
            bot._get_history(uid)
        assert len(bot.user_history) == limit

        # Access uid=0 to make it most-recently-used
        bot._get_history(0)

        # Adding one more user should evict the least-recently-used (uid=1)
        bot._get_history(limit)
        assert len(bot.user_history) == limit
        assert 1 not in bot.user_history   # uid=1 was LRU
        assert 0 in bot.user_history       # uid=0 was refreshed, safe
        assert limit in bot.user_history   # just added

    def test_access_refreshes_lru_position(self):
        # Put uid=10 in first, then uid=20
        bot._get_history(10)
        bot._get_history(20)
        # Re-access uid=10 — it should now be more recent than uid=20
        bot._get_history(10)
        # The first key (LRU) should now be uid=20
        lru_uid = next(iter(bot.user_history))
        assert lru_uid == 20

    def test_size_never_exceeds_max(self):
        for uid in range(bot.MAX_HISTORY_USERS + 50):
            bot._get_history(uid)
        assert len(bot.user_history) <= bot.MAX_HISTORY_USERS


# ── Admin ID parsing ──────────────────────────────────────────────────────────

class TestAdminIds:
    def _parse(self, raw: str) -> frozenset:
        os.environ["ADMIN_USER_IDS"] = raw
        result = bot._parse_admin_ids()
        del os.environ["ADMIN_USER_IDS"]
        return result

    def test_empty_string_returns_empty_set(self):
        assert self._parse("") == frozenset()

    def test_single_id(self):
        assert self._parse("123456") == frozenset({123456})

    def test_multiple_ids(self):
        assert self._parse("111,222,333") == frozenset({111, 222, 333})

    def test_ids_with_whitespace(self):
        assert self._parse("  111 , 222 , 333  ") == frozenset({111, 222, 333})

    def test_ignores_non_numeric_parts(self):
        assert self._parse("111,abc,222") == frozenset({111, 222})

    def test_ignores_empty_parts_from_trailing_comma(self):
        assert self._parse("111,222,") == frozenset({111, 222})

    def test_returns_frozenset(self):
        result = self._parse("42")
        assert isinstance(result, frozenset)

    def test_duplicate_ids_deduplicated(self):
        assert self._parse("100,100,100") == frozenset({100})


# ── Uptime formatting ─────────────────────────────────────────────────────────

class TestFormatUptime:
    def test_returns_unknown_when_no_start_time(self):
        original = bot.BOT_START_TIME
        bot.BOT_START_TIME = None
        try:
            assert bot._format_uptime() == "desconocido"
        finally:
            bot.BOT_START_TIME = original

    def test_shows_minutes_and_seconds_under_one_hour(self):
        bot.BOT_START_TIME = datetime.now() - timedelta(minutes=5, seconds=30)
        result = bot._format_uptime()
        assert "m" in result
        assert "h" not in result

    def test_shows_hours_and_minutes_over_one_hour(self):
        bot.BOT_START_TIME = datetime.now() - timedelta(hours=2, minutes=15)
        result = bot._format_uptime()
        assert "h" in result
        assert "2h" in result


# ── Modifier validation ───────────────────────────────────────────────────────

class TestModifierValidation:
    def test_modifier_at_positive_limit_valid(self):
        s = bot.parse_roll(f"1d6+{bot.MAX_MODIFIER}")
        assert s.modifier == bot.MAX_MODIFIER

    def test_modifier_at_negative_limit_valid(self):
        s = bot.parse_roll(f"1d6-{bot.MAX_MODIFIER}")
        assert s.modifier == -bot.MAX_MODIFIER

    def test_modifier_exceeds_positive_limit_raises(self):
        with pytest.raises(ValueError):
            bot.parse_roll(f"1d6+{bot.MAX_MODIFIER + 1}")

    def test_modifier_exceeds_negative_limit_raises(self):
        with pytest.raises(ValueError):
            bot.parse_roll(f"1d6-{bot.MAX_MODIFIER + 1}")

    def test_zero_modifier_valid(self):
        s = bot.parse_roll("1d6")
        assert s.modifier == 0

    def test_selector_zero_raises(self):
        with pytest.raises(ValueError):
            bot.parse_roll("4d6kh0")


# ── format_stats ──────────────────────────────────────────────────────────────

class TestFormatStats:
    def _make(self, expr: str = "3d6"):
        spec = bot.parse_roll(expr)
        rolls = [bot.execute_roll(spec) for _ in range(bot.STATS_ROLLS)]
        return spec, rolls

    def test_contains_stats_header(self):
        spec, rolls = self._make()
        assert "Estadísticas" in bot.format_stats(spec, rolls)

    def test_contains_all_tirada_lines(self):
        spec, rolls = self._make()
        text = bot.format_stats(spec, rolls)
        for i in range(1, bot.STATS_ROLLS + 1):
            assert f"Tirada {i}" in text

    def test_sum_matches_actual_totals(self):
        spec, rolls = self._make()
        text = bot.format_stats(spec, rolls)
        expected = sum(r.total for r in rolls)
        assert f"Suma: {expected}" in text

    def test_contains_promedio(self):
        spec, rolls = self._make()
        assert "Promedio" in bot.format_stats(spec, rolls)

    def test_output_within_max_msg_len(self):
        spec, rolls = self._make()
        assert len(bot.format_stats(spec, rolls)) <= bot.MAX_MSG_LEN

    def test_variant_label_present(self):
        spec, rolls = self._make("4d6dl1")
        text = bot.format_stats(spec, rolls)
        assert "4d6dl1" in text


# ── history_line / stats_history_line ────────────────────────────────────────

class TestHistoryLines:
    def test_history_line_contains_expr_and_total(self):
        spec = bot.parse_roll("2d6+3")
        result = bot.execute_roll(spec)
        line = bot.history_line(spec, result)
        assert "2d6+3" in line
        assert str(result.total) in line
        assert "→" in line

    def test_stats_history_line_contains_expr(self):
        spec = bot.parse_roll("3d6")
        rolls = [bot.execute_roll(spec) for _ in range(bot.STATS_ROLLS)]
        line = bot.stats_history_line(spec, rolls)
        assert "3d6" in line
        assert "stats" in line

    def test_stats_history_line_contains_all_totals(self):
        spec = bot.parse_roll("3d6")
        rolls = [bot.execute_roll(spec) for _ in range(bot.STATS_ROLLS)]
        line = bot.stats_history_line(spec, rolls)
        for r in rolls:
            assert str(r.total) in line


# ── _is_private ───────────────────────────────────────────────────────────────

class TestIsPrivate:
    def _update(self, chat_type):
        chat = types.SimpleNamespace(type=chat_type)
        return types.SimpleNamespace(effective_chat=chat)

    def test_private_returns_true(self):
        assert bot._is_private(self._update("private")) is True

    def test_group_returns_false(self):
        assert bot._is_private(self._update("group")) is False

    def test_supergroup_returns_false(self):
        assert bot._is_private(self._update("supergroup")) is False

    def test_channel_returns_false(self):
        assert bot._is_private(self._update("channel")) is False

    def test_no_chat_returns_false(self):
        update = types.SimpleNamespace(effective_chat=None)
        assert bot._is_private(update) is False


# ── History persistence ───────────────────────────────────────────────────────

class TestHistoryPersistence:
    """Tests for _load_history and _save_history_to_disk. No Telegram needed."""

    def setup_method(self):
        bot.user_history.clear()

    def teardown_method(self):
        bot.user_history.clear()

    # ── _load_history ─────────────────────────────────────────────────────────

    def test_load_missing_file_does_not_crash(self, tmp_path):
        original = bot.HISTORY_FILE
        bot.HISTORY_FILE = tmp_path / "nonexistent.json"
        try:
            bot._load_history()
            assert len(bot.user_history) == 0
        finally:
            bot.HISTORY_FILE = original

    def test_load_corrupted_file_does_not_crash(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json {{{", encoding="utf-8")
        original = bot.HISTORY_FILE
        bot.HISTORY_FILE = bad
        try:
            bot._load_history()
            assert len(bot.user_history) == 0
        finally:
            bot.HISTORY_FILE = original

    def test_load_restores_entries(self, tmp_path):
        data = {"42": ["3d6 → 12", "1d20 → 17"]}
        f = tmp_path / "hist.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        original = bot.HISTORY_FILE
        bot.HISTORY_FILE = f
        try:
            bot._load_history()
            assert 42 in bot.user_history
            assert list(bot.user_history[42]) == ["3d6 → 12", "1d20 → 17"]
        finally:
            bot.HISTORY_FILE = original

    def test_load_respects_history_maxlen(self, tmp_path):
        many = [f"1d6 → {i}" for i in range(bot.HISTORY_MAXLEN + 5)]
        f = tmp_path / "hist.json"
        f.write_text(json.dumps({"99": many}), encoding="utf-8")
        original = bot.HISTORY_FILE
        bot.HISTORY_FILE = f
        try:
            bot._load_history()
            assert len(bot.user_history[99]) == bot.HISTORY_MAXLEN
        finally:
            bot.HISTORY_FILE = original

    def test_load_ignores_non_digit_keys(self, tmp_path):
        data = {"not_a_uid": ["3d6 → 5"], "also-bad": ["1d20 → 10"]}
        f = tmp_path / "hist.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        original = bot.HISTORY_FILE
        bot.HISTORY_FILE = f
        try:
            bot._load_history()
            assert len(bot.user_history) == 0
        finally:
            bot.HISTORY_FILE = original

    def test_load_skips_non_string_entries(self, tmp_path):
        data = {"77": ["valid → 5", 42, None, "also valid → 10"]}
        f = tmp_path / "hist.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        original = bot.HISTORY_FILE
        bot.HISTORY_FILE = f
        try:
            bot._load_history()
            assert list(bot.user_history[77]) == ["valid → 5", "also valid → 10"]
        finally:
            bot.HISTORY_FILE = original

    # ── _save_history_to_disk ─────────────────────────────────────────────────

    def test_save_writes_valid_json(self, tmp_path):
        bot.user_history[1] = deque(["3d6 → 10", "1d20 → 5"], maxlen=bot.HISTORY_MAXLEN)
        dest = tmp_path / "saved.json"
        original = bot.HISTORY_FILE
        bot.HISTORY_FILE = dest
        try:
            snapshot = {str(uid): list(dq) for uid, dq in bot.user_history.items()}
            bot._save_history_to_disk(snapshot)
            loaded = json.loads(dest.read_text(encoding="utf-8"))
            assert loaded["1"] == ["3d6 → 10", "1d20 → 5"]
        finally:
            bot.HISTORY_FILE = original

    def test_save_leaves_no_tmp_file(self, tmp_path):
        dest = tmp_path / "saved.json"
        original = bot.HISTORY_FILE
        bot.HISTORY_FILE = dest
        try:
            bot._save_history_to_disk({"5": ["1d6 → 3"]})
            assert not dest.with_suffix(".tmp").exists()
        finally:
            bot.HISTORY_FILE = original

    def test_roundtrip_save_and_load(self, tmp_path):
        bot.user_history[100] = deque(["4d6dl1 → 14", "1d20 → 20"], maxlen=bot.HISTORY_MAXLEN)
        dest = tmp_path / "rtrip.json"
        original = bot.HISTORY_FILE
        bot.HISTORY_FILE = dest
        try:
            snapshot = {str(uid): list(dq) for uid, dq in bot.user_history.items()}
            bot._save_history_to_disk(snapshot)
            bot.user_history.clear()
            bot._load_history()
            assert 100 in bot.user_history
            assert list(bot.user_history[100]) == ["4d6dl1 → 14", "1d20 → 20"]
        finally:
            bot.HISTORY_FILE = original


# ── Inline mode never bakes a real roll into the message content ────────────
#
# Security regression tests: inline mode used to precompute real rolls via
# execute_roll() and embed them in the message content, which could be
# scheduled for later delivery in Telegram clients — letting a player
# precompute a favorable roll and send it later as if it happened live.
#
# Fix under test: inline_query() never calls execute_roll() and never puts
# a resolved number in the message text — it only attaches a "reveal"
# button. The real roll happens inside inline_reveal_callback(), triggered
# by a live tap on the button, which can only happen once the message
# actually exists in a chat (immediately or after a scheduled delivery).

class _FakeInlineQuery:
    def __init__(self, query: str):
        self.query = query
        self.answered_with = None
        self.answered_cache_time = None

    async def answer(self, results, cache_time=None):
        self.answered_with = results
        self.answered_cache_time = cache_time


class _FakeUpdate:
    def __init__(self, query: str):
        self.inline_query = _FakeInlineQuery(query)


class TestInlineNeverRolls:
    @pytest.mark.parametrize("query", ["", "1d20", "d20", "2d6", "stats", "stats heroic", "not a roll"])
    def test_execute_roll_never_called(self, query, monkeypatch):
        calls = []
        monkeypatch.setattr(bot, "execute_roll", lambda spec: calls.append(spec) or (_ for _ in ()).throw(
            AssertionError("execute_roll() must never be called from inline_query")
        ))
        update = _FakeUpdate(query)
        asyncio.run(bot.inline_query(update, None))
        assert calls == []
        assert update.inline_query.answered_with is not None

    @pytest.mark.parametrize("query", ["", "1d20", "d20", "2d6", "stats", "stats heroic"])
    def test_valid_queries_attach_reveal_button_with_no_resolved_number(self, query):
        update = _FakeUpdate(query)
        asyncio.run(bot.inline_query(update, None))
        results = update.inline_query.answered_with
        assert update.inline_query.answered_cache_time == 0
        for r in results:
            reply_markup = getattr(r, "reply_markup", None)
            assert reply_markup is not None, "valid roll/stats results must carry a reveal button"
            content = r.input_message_content
            assert "Resultado" not in content.args[0]
            assert "Total" not in content.args[0]
            assert "revela" in content.args[0].lower()

    def test_invalid_roll_expression_has_no_button(self):
        update = _FakeUpdate("not a roll")
        asyncio.run(bot.inline_query(update, None))
        results = update.inline_query.answered_with
        assert len(results) == 1
        assert getattr(results[0], "reply_markup", None) is None

    def test_invalid_stats_variant_has_no_button(self):
        update = _FakeUpdate("stats xyz_invalid_99")
        asyncio.run(bot.inline_query(update, None))
        results = update.inline_query.answered_with
        assert len(results) == 1
        assert getattr(results[0], "reply_markup", None) is None


# ── Inline reveal callback (real roll happens only on live button tap) ──────

class _FakeCallbackQuery:
    def __init__(self, data: str):
        self.data = data
        self.answered = None
        self.edited_text = None
        self.edited_kwargs = None

    async def answer(self, text=None, show_alert=False):
        self.answered = (text, show_alert)

    async def edit_message_text(self, text, **kwargs):
        self.edited_text = text
        self.edited_kwargs = kwargs


class _FakeCallbackUpdate:
    def __init__(self, data: str):
        self.callback_query = _FakeCallbackQuery(data)


class TestInlineRevealCallback:
    def test_roll_reveal_calls_execute_roll_and_edits_message(self):
        update = _FakeCallbackUpdate("r:1d20")
        asyncio.run(bot.inline_reveal_callback(update, None))
        cq = update.callback_query
        assert cq.answered is not None
        assert cq.edited_text is not None
        assert "1d20" in cq.edited_text
        assert cq.edited_kwargs["reply_markup"] is None

    def test_stats_reveal_calls_execute_roll_and_edits_message(self):
        update = _FakeCallbackUpdate("s:4d6dl1")
        asyncio.run(bot.inline_reveal_callback(update, None))
        cq = update.callback_query
        assert cq.edited_text is not None
        assert "4d6dl1" in cq.edited_text
        assert "Estadísticas" in cq.edited_text

    def test_execute_roll_only_runs_on_reveal_not_before(self, monkeypatch):
        calls = []
        original = bot.execute_roll
        def spy(spec):
            calls.append(spec)
            return original(spec)
        monkeypatch.setattr(bot, "execute_roll", spy)
        assert calls == []
        update = _FakeCallbackUpdate("r:2d6")
        asyncio.run(bot.inline_reveal_callback(update, None))
        assert len(calls) == 1

    def test_invalid_roll_payload_does_not_execute_roll(self, monkeypatch):
        monkeypatch.setattr(bot, "execute_roll", lambda spec: (_ for _ in ()).throw(
            AssertionError("execute_roll() must not run for an invalid payload")
        ))
        update = _FakeCallbackUpdate("r:not-a-roll")
        asyncio.run(bot.inline_reveal_callback(update, None))
        cq = update.callback_query
        assert cq.answered[1] is True   # show_alert
        assert cq.edited_text is None

    def test_unknown_kind_is_a_no_op(self):
        update = _FakeCallbackUpdate("x:whatever")
        asyncio.run(bot.inline_reveal_callback(update, None))
        cq = update.callback_query
        assert cq.answered is not None
        assert cq.edited_text is None
