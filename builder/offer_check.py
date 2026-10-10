"""Generated code for the offer steps: per-product facts, offer check, promise values.

All brief rules arrive as spec data (``offer`` section) and are embedded in the
snippets as JSON. The snippets read and write only ``vars``, never raise, and contain
no double braces.
"""

from __future__ import annotations

import json
from typing import Any

from .prompts import OFFER_VERDICT_MESSAGES
from .spec import PhoneAgentSpec

# Workflow variables owned by the offer steps (framework names, not brief data).
OFFER_DATE = "offer_date"
OFFER_AMOUNT = "offer_amount"
OFFER_AMOUNT_KIND = "offer_amount_kind"
OFFER_PRODUCT = "offer_product_number"
OFFER_PROGRESS = "offer_progress"
OFFERS_ACCEPTED = "offers_accepted"
OFFERS_ACCEPTED_COUNT = "offers_accepted_count"
OFFERS_NOTED = "offers_noted"


def _py_literal(value: Any) -> str:
    """A Python expression that rebuilds ``value`` from JSON without any brace characters."""
    text = json.dumps(json.dumps(value, sort_keys=True))
    return "json.loads(" + text.replace("{", "\\u007b").replace("}", "\\u007d") + ")"


def _verdict_messages() -> dict[str, str]:
    messages = {}
    for line in OFFER_VERDICT_MESSAGES.text.splitlines():
        key, _, sentence = line.partition(": ")
        messages[key.strip()] = sentence.strip()
    return messages


def _config(spec: PhoneAgentSpec, reset_variables: list[str]) -> dict[str, Any]:
    offer = spec.offer.data
    return {
        "offer": {key: value for key, value in offer.items() if key != "rules"},
        "products_variable": spec.account.data["products_variable"],
        "products_field": spec.account.data["products_field"],
        "product_id_field": spec.account.data["product_id_field"],
        # Customer-facing product name (F-044); optional spec fields.
        "kind_field": spec.account.data.get("product_kind_field") or "",
        "label_field": spec.account.data.get("product_label_field") or "",
        "reset": reset_variables,
        "messages": _verdict_messages(),
    }


def product_reader_code(products_variable: str, products_field: str) -> str:
    """Return the one product reader used by offer code, hooks, and special paths."""
    return f"""PRODUCTS_VARIABLE = {products_variable!r}
PRODUCTS_FIELD = {products_field!r}


def as_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = []
    return value if isinstance(value, list) else []


def put_path(target, path, value):
    current = target
    for part in path[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = dict()
            current[part] = child
        current = child
    if path:
        current[path[-1]] = value


def load_products():
    products = as_list(vars.get(PRODUCTS_VARIABLE))
    if products:
        return [item for item in products if isinstance(item, dict)]
    exact = re.compile(r'^[A-Za-z0-9_]+_response\\.data\\.' + re.escape(PRODUCTS_FIELD) + r'$')
    for key, value in vars.items():
        if exact.fullmatch(str(key)):
            products = as_list(value)
            if products:
                return [item for item in products if isinstance(item, dict)]
    flat = re.compile(r'^([A-Za-z0-9_]+_response\\.data\\.' + re.escape(PRODUCTS_FIELD) + r')\\.(\\d+)\\.(.+)$')
    rebuilt_by_source = dict()
    for key, value in vars.items():
        match = flat.fullmatch(str(key))
        if not match:
            continue
        source = match.group(1)
        index = int(match.group(2))
        path = match.group(3).split('.')
        item = rebuilt_by_source.setdefault(source, dict()).setdefault(index, dict())
        put_path(item, path, value)
    for rebuilt in rebuilt_by_source.values():
        products = [rebuilt[index] for index in sorted(rebuilt)]
        if products:
            return products
    return []
"""


PRELUDE = """import datetime
import json
import re
CONFIG = __CONFIG__
OFFER = CONFIG['offer']
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

__PRODUCT_READER__


def parse_day(value):
    text = str(value or '').strip()
    match = re.search(r'(\\d{4})-(\\d{1,2})-(\\d{1,2})', text)
    if not match:
        return None
    try:
        return datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except Exception:
        return None


def normalized_date_text(value):
    text = str(value or '').strip().lower()
    text = re.sub(r'(?<=\\d)(st|nd|rd|th)\\b', '', text)
    text = re.sub(r'[^a-z0-9 ]+', ' ', text)
    return re.sub(r'\\s+', ' ', text).strip()


def first_day_number(start, wanted):
    for month_offset in range(13):
        year = start.year + (start.month - 1 + month_offset) // 12
        month = (start.month - 1 + month_offset) % 12 + 1
        try:
            candidate = datetime.date(year, month, wanted)
        except Exception:
            continue
        if candidate >= start:
            return candidate
    return None


def resolve_offer_day(value):
    direct = parse_day(value)
    if direct is not None:
        return direct
    text = normalized_date_text(value)
    if not text:
        return None
    start = today()
    if text == 'today':
        return start
    if text == 'tomorrow':
        return start + datetime.timedelta(days=1)
    if text in ('day after tomorrow', 'the day after tomorrow'):
        return start + datetime.timedelta(days=2)
    weekday_names = [name.lower() for name in WEEKDAYS]
    weekday = next((index for index, name in enumerate(weekday_names) if re.search(r'\\b' + name + r'\\b', text)), None)
    if weekday is not None and 'week after next' in text:
        next_monday = start + datetime.timedelta(days=(7 - start.weekday()))
        return next_monday + datetime.timedelta(days=7 + weekday)
    if 'next week' in text and 'week after next' not in text:
        if weekday is None:
            return None
        next_monday = start + datetime.timedelta(days=(7 - start.weekday()))
        return next_monday + datetime.timedelta(days=weekday)
    if weekday is not None:
        numbered = re.search(r'\\b(\\d{1,2})\\b', text)
        if numbered:
            wanted = int(numbered.group(1))
            for month_offset in range(13):
                year = start.year + (start.month - 1 + month_offset) // 12
                month = (start.month - 1 + month_offset) % 12 + 1
                try:
                    candidate = datetime.date(year, month, wanted)
                except Exception:
                    continue
                if candidate >= start and candidate.weekday() == weekday:
                    return candidate
        if 'next ' + weekday_names[weekday] in text:
            if OFFER.get('next_weekday', 'ask') == 'following_week':
                next_monday = start + datetime.timedelta(days=(7 - start.weekday()))
                return next_monday + datetime.timedelta(days=weekday)
            delta = (weekday - start.weekday()) % 7
            delta = delta or 7
        elif 'this ' + weekday_names[weekday] in text:
            this_monday = start - datetime.timedelta(days=start.weekday())
            return this_monday + datetime.timedelta(days=weekday)
        else:
            delta = (weekday - start.weekday()) % 7
            delta = delta or 7
        return start + datetime.timedelta(days=delta)
    month_aliases = dict()
    for index, name in enumerate(MONTHS):
        month_aliases[name.lower()] = index + 1
        month_aliases[name[:3].lower()] = index + 1
    month = next((number for name, number in month_aliases.items() if re.search(r'\\b' + name + r'\\b', text)), None)
    numbered = re.search(r'\\b(\\d{1,2})\\b', text)
    if month is not None and numbered:
        year_match = re.search(r'\\b(\\d{4})\\b', text)
        year = int(year_match.group(1)) if year_match else start.year
        try:
            candidate = datetime.date(year, month, int(numbered.group(1)))
            if not year_match and candidate < start:
                candidate = datetime.date(year + 1, month, int(numbered.group(1)))
            return candidate
        except Exception:
            return None
    only_day = re.fullmatch(r'(?:(?:on )?(?:the )?)?(\\d{1,2})', text)
    if only_day:
        wanted = int(only_day.group(1))
        if 1 <= wanted <= 31:
            return first_day_number(start, wanted)
    return None


def ambiguous_next_weekday(value, day):
    if day is None:
        return False
    if OFFER.get('next_weekday', 'ask') != 'ask':
        return False
    text = normalized_date_text(value)
    if 'next week' in text or 'week after next' in text:
        return False
    weekday_names = [name.lower() for name in WEEKDAYS]
    weekday = next((index for index, name in enumerate(weekday_names) if re.search(r'\\bnext ' + name + r'\\b', text)), None)
    if weekday is None:
        return False
    start = today()
    return day <= start + datetime.timedelta(days=(6 - start.weekday()))


def parse_amount(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r'[^0-9.,]', '', str(value or ''))
    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')
    elif ',' in text:
        parts = text.split(',')
        if len(parts[-1]) == 3 or len(parts) > 2:
            text = text.replace(',', '')
        else:
            text = text.replace(',', '.')
    elif text.count('.') > 1:
        text = text.replace('.', '')
    try:
        return float(text)
    except Exception:
        return None


def today():
    day = parse_day(vars.get(OFFER['today_variable']))
    return day or datetime.date.today()


def is_business(day):
    return day.isoweekday() not in OFFER['non_business_weekdays'] and day.isoformat() not in OFFER['holidays']


def shift_to_business(day, step):
    for _ in range(400):
        if is_business(day):
            return day
        day = day + datetime.timedelta(days=step)
    return day


def add_days(start, rule):
    days = int(rule.get('days') or 0)
    if rule.get('unit') == 'business':
        day = start
        counted = 0
        for _ in range(4000):
            if counted >= days:
                break
            day = day + datetime.timedelta(days=1)
            if is_business(day):
                counted += 1
        return day
    return start + datetime.timedelta(days=days)


def matches(product, conditions):
    for condition in conditions or []:
        value = product.get(condition.get('field'))
        if 'equals' in condition and str(value) != str(condition['equals']):
            return False
        if 'in' in condition and str(value) not in [str(item) for item in condition['in']]:
            return False
        for key in ('min', 'max'):
            if key in condition:
                number = parse_amount(value)
                if number is None:
                    return False
                if key == 'min' and number < float(condition[key]):
                    return False
                if key == 'max' and number > float(condition[key]):
                    return False
    return True


def first_rule(product, rules):
    for rule in rules or []:
        if matches(product, rule.get('when')):
            return rule
    return None


def amount_limit(product, rules):
    rule = first_rule(product, rules)
    if rule is None:
        return None
    if 'value' in rule:
        base = parse_amount(rule['value'])
    else:
        base = parse_amount(product.get(rule.get('field')))
    if base is None:
        return None
    return round(base * float(rule.get('share', 1)), 2)


def rejected_offer_limit(product):
    rule = first_rule(product, OFFER.get('max_rejected_offers_by_product', []))
    return int(rule.get('value')) if rule is not None else int(OFFER['max_rejected_offers'])


def earliest_counted():
    return add_days(today(), OFFER['earliest'])


def limits(product):
    start = today()
    earliest = earliest_counted()
    if OFFER['promise_date_must_be_business_day']:
        earliest = shift_to_business(earliest, 1)
    latest = None
    rule = first_rule(product, OFFER['latest'])
    if rule is not None:
        latest = add_days(start, rule)
        if rule.get('unit') != 'business' and OFFER['latest_on_non_business_day'] != 'keep':
            latest = shift_to_business(latest, -1 if OFFER['latest_on_non_business_day'] == 'previous' else 1)
    return earliest, latest, amount_limit(product, OFFER['min_amount']), amount_limit(product, OFFER['max_amount'])


def say_day(day):
    return WEEKDAYS[day.weekday()] + ' ' + day.isoformat() if day else 'none'


def say_confirmation_day(day):
    return WEEKDAYS[day.weekday()] + ' ' + str(day.day) + ' ' + MONTHS[day.month - 1] if day else 'none'


def say_amount(amount):
    return ('%.2f' % amount) if amount is not None else 'none'


def say_spoken_day(day):
    # "Wednesday, 14 October"; the year only when it is not this year.
    if not day:
        return 'none'
    text = WEEKDAYS[day.weekday()] + ', ' + str(day.day) + ' ' + MONTHS[day.month - 1]
    return text + (' ' + str(day.year) if day.year != today().year else '')


def say_spoken_amount(amount):
    # 420 instead of 420.00; cents only when there are cents.
    if amount is None:
        return 'none'
    if abs(amount - round(amount)) < 0.005:
        return str(int(round(amount)))
    return '%.2f' % amount


ORDINALS = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth']


def product_name(index, product, count):
    # Customer-facing name: kind in words plus the label field ("credit card ending 4821").
    kind = product.get(CONFIG['kind_field']) if CONFIG['kind_field'] else None
    label = product.get(CONFIG['label_field']) if CONFIG['label_field'] else None
    words = str(kind).replace('_', ' ').strip() if kind not in (None, '') else ''
    if label not in (None, ''):
        words = (words or 'product') + ' ending ' + str(label)
    if words:
        return words
    if count > 1 and 1 <= index <= len(ORDINALS):
        return 'the ' + ORDINALS[index - 1] + ' product'
    return 'the product'


def product_facts(index, product):
    earliest, latest, low, high = limits(product)
    shown = ', '.join(
        str(key) + ' ' + str(value) for key, value in product.items()
        if key != CONFIG['product_id_field'] and not isinstance(value, (dict, list))
    )
    return (
        'Product ' + str(index) + ': ' + shown + '. Earliest date ' + say_day(earliest)
        + '; latest date ' + say_day(latest) + '; minimum amount ' + say_amount(low)
        + '; maximum amount ' + say_amount(high) + '. Name it to the customer as: '
        + product_name(index, product, len(load_products())) + '.'
    )


def accepted_offers():
    value = vars.get(CONFIG['accepted'])
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = None
    return value if isinstance(value, dict) else dict()


def noted_numbers():
    value = vars.get(CONFIG['noted'])
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = None
    result = []
    for item in value if isinstance(value, list) else []:
        try:
            result.append(int(item))
        except Exception:
            pass
    return result


def handled_numbers(accepted):
    # Products with an accepted offer or a recorded note.
    numbers = set(noted_numbers())
    for key in accepted:
        try:
            numbers.add(int(key))
        except Exception:
            pass
    return numbers


def summary(accepted):
    # Read-back in spoken words (F-044). The product number in brackets is for the promise tool only.
    products = load_products()
    lines = []
    for key in sorted(accepted, key=lambda item: int(item) if str(item).isdigit() else 0):
        entry = accepted[key]
        number = int(key) if str(key).isdigit() else 0
        product = products[number - 1] if 1 <= number <= len(products) else dict()
        lines.append(
            product_name(number, product, len(products)) + ': '
            + say_spoken_amount(parse_amount(entry.get('amount'))) + ' on '
            + say_spoken_day(parse_day(entry.get('date'))) + ' [product number ' + str(key) + ']'
        )
    return '; '.join(lines) or 'none'
"""


SETUP_BODY = """try:
    lines = [product_facts(index, product) for index, product in enumerate(load_products(), start=1)]
    vars['products_facts'] = ' '.join(lines) or 'No products were returned.'
    vars['today_text'] = say_day(today())
except Exception:
    vars['products_facts'] = 'No product facts are available.'
    vars['today_text'] = 'unknown'
vars[CONFIG['accepted']] = json.dumps(dict())
vars[CONFIG['accepted_count']] = 0
vars[CONFIG['noted']] = json.dumps([])
vars['offers_summary'] = 'none'
vars['offer_message'] = 'No offer has been checked yet.'
vars['offer_verdict'] = 'none'
vars['offer_rejections'] = 0
vars['offer_last_signature'] = ''
vars['offer_rejections_by_product'] = json.dumps(dict())
vars['offer_last_signatures_by_product'] = json.dumps(dict())
vars[CONFIG['amount_kind_var']] = ''
vars[CONFIG['progress']] = 'none'
"""


CHECK_BODY = """verdict = 'missing'
suggest_day = None
suggest_amount = None
number = None
progress = 'rejected'
product = None
try:
    products = load_products()
    raw_number = vars.get(CONFIG['product_var'])
    try:
        number = int(str(raw_number).strip())
    except Exception:
        number = 1 if len(products) == 1 else None
    raw_day = vars.get(CONFIG['date_var'])
    day = resolve_offer_day(raw_day)
    amount = parse_amount(vars.get(CONFIG['amount_var']))
    if number is None or not (1 <= number <= len(products)):
        verdict = 'product_unknown'
    elif day is None:
        verdict = 'missing'
    elif ambiguous_next_weekday(raw_day, day):
        verdict = 'date_ambiguous'
        suggest_day = day
    else:
        product = products[number - 1]
        earliest, latest, low, high = limits(product)
        amount_kind = str(vars.get(CONFIG['amount_kind_var']) or '').strip().lower()
        if amount is None and amount_kind == 'full':
            amount = high
        elif amount is None and amount_kind == 'minimum':
            amount = low
        if amount is None or amount <= 0:
            verdict = 'missing'
        elif day < earliest:
            # Before the counted earliest date: too early. On or after it, the date was only
            # moved because it is not a business day (for example today is a holiday).
            verdict = 'date_not_business_day' if day >= earliest_counted() else 'date_too_early'
            suggest_day = earliest
        elif latest is not None and day > latest:
            verdict = 'date_too_late'
            suggest_day = latest
        elif OFFER['promise_date_must_be_business_day'] and not is_business(day):
            verdict = 'date_not_business_day'
            suggest_day = shift_to_business(day, 1)
            if latest is not None and suggest_day > latest:
                suggest_day = latest
        elif low is not None and amount < low - 0.005:
            verdict = 'amount_too_low'
            suggest_amount = low
        elif high is not None and amount > high + 0.005:
            verdict = 'amount_too_high'
            suggest_amount = high
        else:
            verdict = 'ok'
            accepted = accepted_offers()
            accepted[str(number)] = dict(
                product_id=product.get(CONFIG['product_id_field']), date=day.isoformat(), amount=round(amount, 2)
            )
            vars[CONFIG['accepted']] = json.dumps(accepted)
            vars[CONFIG['accepted_count']] = len(accepted)
            vars['offers_summary'] = summary(accepted)
            # Ready when every returned product has an accepted offer or a note.
            progress = 'ready' if len(handled_numbers(accepted)) >= len(products) else 'more'
    signature = str(number) + '|' + str(vars.get(CONFIG['date_var'])) + '|' + str(vars.get(CONFIG['amount_var'])) + '|' + str(vars.get(CONFIG['amount_kind_var']))
    if verdict not in ('ok', 'missing', 'product_unknown', 'date_ambiguous'):
        rejection_key = str(number)
        rejection_counts = vars.get('offer_rejections_by_product')
        last_signatures = vars.get('offer_last_signatures_by_product')
        for name, value in (('counts', rejection_counts), ('signatures', last_signatures)):
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except Exception:
                    value = None
            if name == 'counts':
                rejection_counts = value if isinstance(value, dict) else dict()
            else:
                last_signatures = value if isinstance(value, dict) else dict()
        try:
            rejections = int(rejection_counts.get(rejection_key) or 0)
        except Exception:
            rejections = 0
        if signature != str(last_signatures.get(rejection_key) or ''):
            rejections += 1
        rejection_counts[rejection_key] = rejections
        last_signatures[rejection_key] = signature
        vars['offer_rejections_by_product'] = json.dumps(rejection_counts)
        vars['offer_last_signatures_by_product'] = json.dumps(last_signatures)
        vars['offer_rejections'] = rejections
        if rejections >= rejected_offer_limit(product):
            noted = noted_numbers()
            if number not in noted:
                noted.append(number)
            vars[CONFIG['noted']] = json.dumps(noted)
            accepted = accepted_offers()
            if len(handled_numbers(accepted)) >= len(products):
                progress = 'ready' if accepted else 'limit'
            else:
                progress = 'more'
    vars['offer_last_signature'] = signature
except Exception:
    verdict = 'missing'
    progress = 'rejected'
message = CONFIG['messages'].get(verdict, CONFIG['messages'].get('missing', ''))
shown_day = say_confirmation_day(suggest_day) if verdict == 'date_ambiguous' else say_day(suggest_day)
message = message.replace('[date]', shown_day).replace('[amount]', say_amount(suggest_amount))
message = message.replace('[product]', str(number) if number is not None else 'unknown')
if progress == 'more':
    message = message + ' ' + CONFIG['messages'].get('more', '')
vars['offer_verdict'] = verdict
vars['offer_message'] = message
vars['offer_suggested_date'] = suggest_day.isoformat() if suggest_day else ''
vars['offer_suggested_amount'] = suggest_amount if suggest_amount is not None else ''
vars[CONFIG['progress']] = progress
vars[CONFIG['date_var']] = ''
vars[CONFIG['amount_var']] = ''
vars[CONFIG['amount_kind_var']] = ''
for name in CONFIG['reset']:
    vars[name] = ''
"""


PROMISE_HOOK_BODY = """try:
    body = config.get('body')
    accepted = accepted_offers()
    if isinstance(body, dict) and accepted:
        choice = body.get(CONFIG['number_field'])
        try:
            key = str(int(str(choice).strip()))
        except Exception:
            key = ''
        if key not in accepted and len(accepted) == 1:
            key = list(accepted)[0]
        entry = accepted.get(key)
        if isinstance(entry, dict):
            body.pop(CONFIG['number_field'], None)
            body[CONFIG['id_field']] = entry.get('product_id')
            body[CONFIG['date_field']] = entry.get('date')
            body[CONFIG['amount_field']] = entry.get('amount')
except Exception:
    pass
"""


NOTED_BODY = """progress = 'open'
try:
    if str(vars.get(CONFIG['result_var']) or '').lower() == 'true' and CONFIG['number_arg']:
        raw = vars.get(CONFIG['number_arg'])
        if raw is None:
            args = vars.get(CONFIG['args_var'])
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = None
            if isinstance(args, dict):
                raw = args.get(CONFIG['number_field'])
        number = int(str(raw).strip())
        noted = noted_numbers()
        if number not in noted:
            noted.append(number)
        vars[CONFIG['noted']] = json.dumps(noted)
    products = load_products()
    accepted = accepted_offers()
    if products and accepted and len(handled_numbers(accepted)) >= len(products):
        progress = 'ready'
except Exception:
    pass
vars[CONFIG['progress']] = progress
"""


def _full_config(spec: PhoneAgentSpec, reset_variables: list[str]) -> dict[str, Any]:
    config = _config(spec, reset_variables)
    config.update({
        "accepted": OFFERS_ACCEPTED, "accepted_count": OFFERS_ACCEPTED_COUNT, "noted": OFFERS_NOTED,
        "progress": OFFER_PROGRESS, "product_var": OFFER_PRODUCT, "date_var": OFFER_DATE,
        "amount_var": OFFER_AMOUNT, "amount_kind_var": OFFER_AMOUNT_KIND,
        "number_field": spec.confirmation.data["product_number_field"],
        "id_field": spec.confirmation.data["promise_product_id_field"],
        "date_field": spec.confirmation.data["promise_date_field"],
        "amount_field": spec.confirmation.data["promise_amount_field"],
    })
    return config


def _code(spec: PhoneAgentSpec, body: str, reset_variables: list[str]) -> str:
    reader = product_reader_code(
        spec.account.data["products_variable"], spec.account.data["products_field"]
    )
    return (
        PRELUDE.replace("__CONFIG__", _py_literal(_full_config(spec, reset_variables)))
        .replace("__PRODUCT_READER__", reader)
        + body
    )


def offer_setup_code(spec: PhoneAgentSpec) -> str:
    """Per-product facts (earliest/latest date, min/max amount) and sentinels for prompts."""
    return _code(spec, SETUP_BODY, [])


def check_offer_code(spec: PhoneAgentSpec, reset_variables: list[str]) -> str:
    """Check the extracted offer against the spec rules; never raises."""
    return _code(spec, CHECK_BODY, reset_variables)


def special_noted_code(spec: PhoneAgentSpec, result_variable: str, tool_name: str, has_number: bool) -> str:
    """After a product-level special path: remember the noted product, report readiness."""
    config = _full_config(spec, [])
    number_field = spec.confirmation.data["product_number_field"]
    config.update({
        "result_var": result_variable,
        "number_arg": tool_name + "_args." + number_field if has_number else "",
        "args_var": tool_name + "_args",
    })
    reader = product_reader_code(
        spec.account.data["products_variable"], spec.account.data["products_field"]
    )
    return (
        PRELUDE.replace("__CONFIG__", _py_literal(config))
        .replace("__PRODUCT_READER__", reader)
        + NOTED_BODY
    )


def promise_values_hook(spec: PhoneAgentSpec) -> str:
    """create_promise pre-hook: product id, date and amount come from checked offers."""
    return _code(spec, PROMISE_HOOK_BODY, [])
