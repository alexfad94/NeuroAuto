# === tests/test_sales_bot.py ===
# Тест-кейсы для Auto Sales Assistant

import pytest
import os

PROMPT_CARD = 'prompts/sales/sales_bot_v3.1_CLEAR_card.md'

def test_prompt_file_exists():
    """Проверка, что карточка промпта с полным текстом существует"""
    assert os.path.exists(PROMPT_CARD), \
        f"Файл не найден: {PROMPT_CARD}"

def test_config_file_exists():
    """Проверка, что конфиг существует"""
    assert os.path.exists('prompts/config/sales_variables.yaml'), \
        "Файл конфига не найден: prompts/config/sales_variables.yaml"

def test_card_file_exists():
    """Проверка, что карточка промпта существует"""
    assert os.path.exists('docs/prompts/sales_bot_card.md'), \
        "Файл карточки не найден: docs/prompts/sales_bot_card.md"

def test_routing_triggers_present():
    """Проверка, что триггеры маршрутизации есть в промпте"""
    with open(PROMPT_CARD, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'ROUTING_FINANCE' in content, "Не найден триггер ROUTING_FINANCE"
    assert 'ROUTING_TRADE_IN' in content, "Не найден триггер ROUTING_TRADE_IN"
    assert 'ROUTING_SERVICE' in content, "Не найден триггер ROUTING_SERVICE"
    assert 'ROUTING_TEST_DRIVE' in content, "Не найден триггер ROUTING_TEST_DRIVE"

def test_variables_in_prompt():
    """Проверка, что переменные {{VARIABLES}} есть в промпте"""
    with open(PROMPT_CARD, 'r', encoding='utf-8') as f:
        content = f.read()
    
    required_variables = [
        '{{COMPANY_NAME}}',
        '{{CHANNEL_NAME}}',
        '{{COMM_CHANNEL}}',
        '{{WORK_HOURS}}',
        '{{TIMEZONE}}',
        '{{SHOWROOM_ADDRESS}}',
        '{{SUPPORT_PHONE}}',
        '{{SUPPORT_EMAIL}}',
        '{{KB_SOURCE}}',
        '{{MAX_DISCOUNT}}',
        '{{CRM_SYSTEM}}',
        '{{EXAMPLE_PRICE}}'
    ]
    
    for var in required_variables:
        assert var in content, f"Не найдена переменная: {var}"

def test_limitations_section():
    """Проверка, что раздел ограничений на месте"""
    with open(PROMPT_CARD, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'LIMITATIONS' in content, "Не найден раздел LIMITATIONS"
    assert 'НЕ выдумывай' in content, "Не найдено ограничение на выдумывание"
    assert 'НЕ обещай скидок' in content, "Не найдено ограничение на скидки"
    assert 'НЕ запрашивай паспортные данные' in content, \
        "Не найдено ограничение на паспортные данные"

def test_yaml_config_structure():
    """Проверка структуры YAML конфига"""
    import yaml
    
    with open('prompts/config/sales_variables.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Проверка основных секций
    assert 'company' in config, "Не найдена секция company"
    assert 'support' in config, "Не найдена секция support"
    assert 'schedule' in config, "Не найдена секция schedule"
    assert 'channels' in config, "Не найдена секция channels"
    assert 'knowledge_base' in config, "Не найдена секция knowledge_base"
    assert 'bitrix24' in config, "Не найдена секция bitrix24"
    assert 'crm' in config, "Не найдена секция crm"
    
    # Проверка вложенных ключей
    assert 'name' in config['company'], "Не найдено company.name"
    assert 'phone' in config['support'], "Не найдено support.phone"
    assert 'routing' in config['bitrix24'], "Не найдено bitrix24.routing"

def test_prompt_length():
    """Проверка, что промпт не слишком короткий"""
    with open(PROMPT_CARD, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.strip().split('\n')
    assert len(lines) > 50, f"Промпт слишком короткий: {len(lines)} строк (минимум 50)"

def test_context_section():
    """Проверка раздела CONTEXT"""
    with open(PROMPT_CARD, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'CONTEXT' in content, "Не найден раздел CONTEXT"
    assert 'автодилера' in content, "Не указано, что это автодилер"
    assert 'Telegram' in content or '{{CHANNEL_NAME}}' in content, \
        "Не указан канал коммуникации"

def test_output_format_section():
    """Проверка раздела OUTPUT FORMAT"""
    with open(PROMPT_CARD, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'OUTPUT FORMAT' in content or 'OUTPUT' in content, \
        "Не найден раздел OUTPUT FORMAT"
    assert 'Пример:' in content, "Не найден пример ответа"