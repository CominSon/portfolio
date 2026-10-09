-- ============================================
-- Таблица мониторинга задач, использующих браузер
-- ============================================
CREATE TABLE IF NOT EXISTS browser_tasks_monitor (
    id SERIAL PRIMARY KEY,
    process_id UUID NOT NULL, -- уникальный идентификатор задачи
    task_type TEXT NOT NULL, -- тип задачи (например, 'pdf_generation')
    payload_json JSONB NOT NULL, -- параметры задачи в формате JSON
    customer_email TEXT NOT NULL, -- адрес заказчика
    profile_name TEXT NOT NULL, -- какой профиль браузера используется
    started_at TIMESTAMP DEFAULT NOW(), -- время старта задачи
    finished_at TIMESTAMP, -- время завершения
    status TEXT CHECK (status IN ('active', 'done', 'failed')) NOT NULL
);

-- Индекс для быстрого поиска активных задач
CREATE INDEX IF NOT EXISTS idx_browser_tasks_active
    ON browser_tasks_monitor (status);

-- Индекс для поиска задач по профилю
CREATE INDEX IF NOT EXISTS idx_browser_tasks_profile
    ON browser_tasks_monitor (profile_name, status);

-- ============================================
-- Таблица ролевой модели (whitelist)
-- ============================================
CREATE TABLE IF NOT EXISTS role_model_users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL, -- почтовый адрес отправителя
    navigator_user_id TEXT, -- id пользователя в навигаторе
    dashboard_ids JSONB, -- список id дешбордов, доступных пользователю
    template_names JSONB, -- список шаблонов, доступных пользователю
    updated_at TIMESTAMP DEFAULT NOW() --дата и время обновления
);
