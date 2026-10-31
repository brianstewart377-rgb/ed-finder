-- Add current OpenAI chat models (GPT-5.4 and newer) to Octopus's model list.
-- Opt-in only: no default, pin or existing row changes. Prices are USD per 1M tokens.
INSERT INTO "available_models"
 ("id","modelId","displayName","provider","category","inputPrice","outputPrice","isActive","isPlatformDefault","sortOrder","createdAt","updatedAt")
VALUES
 ('edf_gpt_6_astra',    'gpt-6-astra',    'GPT-6 Astra',    'openai','llm',10,   50,   true,false,13,now(),now()),
 ('edf_gpt_6_1_sol',    'gpt-6.1-sol',    'GPT-6.1 Sol',    'openai','llm',2,    10,   true,false,14,now(),now()),
 ('edf_gpt_6_1_terra',  'gpt-6.1-terra',  'GPT-6.1 Terra',  'openai','llm',1,    5,    true,false,15,now(),now()),
 ('edf_gpt_6_luna',     'gpt-6-luna',     'GPT-6 Luna',     'openai','llm',0.10, 0.50, true,false,16,now(),now()),
 ('edf_gpt_5_6_sol',    'gpt-5.6-sol',    'GPT-5.6 Sol',    'openai','llm',5,    30,   true,false,17,now(),now()),
 ('edf_gpt_5_6_terra',  'gpt-5.6-terra',  'GPT-5.6 Terra',  'openai','llm',2,    12,   true,false,18,now(),now()),
 ('edf_gpt_5_6_luna',   'gpt-5.6-luna',   'GPT-5.6 Luna',   'openai','llm',0.20, 1.20, true,false,19,now(),now()),
 ('edf_gpt_5_5',        'gpt-5.5',        'GPT-5.5',        'openai','llm',5,    30,   true,false,20,now(),now()),
 ('edf_gpt_5_4',        'gpt-5.4',        'GPT-5.4',        'openai','llm',2.50, 15,   true,false,21,now(),now()),
 ('edf_gpt_5_4_mini',   'gpt-5.4-mini',   'GPT-5.4 mini',   'openai','llm',0.75, 4.50, true,false,22,now(),now())
ON CONFLICT ("modelId") DO NOTHING;
