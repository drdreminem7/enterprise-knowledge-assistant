# Demo Seed

This folder gives you a minimal end-to-end demo setup for the backend.

Before seeding evaluation data, start the backend once after the latest schema changes so the evaluation tables are created:

```bash
python3 -m uvicorn backend.app.main:app --reload
```

## 1. Create a knowledge base

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/knowledge-bases \
  -H "Content-Type: application/json" \
  -d '{"name":"HR Demo","description":"Demo knowledge base for seeded policy questions"}'
```

## 2. Upload the sample document

```bash
curl -X POST http://127.0.0.1:8000/api/documents/upload \
  -F "knowledge_base_id=1" \
  -F "file=@demo/hr_policy_demo.txt"
```

## 3. Seed the evaluation set

```bash
psql enterprise_assistant -f demo/evaluation_seed.sql
```

## 4. Run evaluation

```bash
curl -X POST http://127.0.0.1:8000/api/evaluation/run \
  -H "Content-Type: application/json" \
  -d '{"set_id":1,"knowledge_base_id":1,"top_k":5}'
```

## 5. Try chat

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"knowledge_base_id":1,"question":"What is the remote work policy?","top_k":5}'
```
