-- Migration: Adicionar tabela de log de consumo de tokens da IA (Claude)
--
-- Uma linha por chamada messages.create feita a Claude, com a contagem
-- exata de tokens devolvida por response.usage e uma estimativa de custo.
-- Ver app/models/ai_usage_log.py e app/core/ai_usage.py.

CREATE TABLE IF NOT EXISTS ai_usage_log (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Funcionalidade que originou a chamada (pei_geracao, jornada_terapeutica,
    -- planejamento_anual, analise_qualitativa, prova_reforco, etc.)
    feature VARCHAR(50) NOT NULL,

    -- Modelo Claude usado nesta chamada
    model VARCHAR(100) NOT NULL,

    -- Contagem exata de tokens (response.usage)
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cache_creation_input_tokens INT NOT NULL DEFAULT 0,
    cache_read_input_tokens INT NOT NULL DEFAULT 0,

    -- Estimativa de custo em USD (NULL se o modelo nao estiver na tabela de precos)
    cost_usd DECIMAL(12, 6) NULL,

    -- Atribuicao opcional - SEM foreign key de proposito (tabela de log/telemetria,
    -- nao deve travar nem ser afetada por exclusao de alunos/usuarios/escolas)
    student_id INT NULL,
    user_id INT NULL,
    escola_id INT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_ai_usage_feature (feature),
    INDEX idx_ai_usage_feature_created (feature, created_at),
    INDEX idx_ai_usage_student (student_id),
    INDEX idx_ai_usage_user (user_id),
    INDEX idx_ai_usage_escola (escola_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
