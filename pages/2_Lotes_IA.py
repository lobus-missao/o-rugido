"""Aba Lotes de IA — fluxo manual de análise."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, run_cli, fmt_dt
from news_radar.dashboard_queries import ai_coverage_stats
from news_radar.ai_batches import list_ai_batches, import_ai_result_detailed
from news_radar.config import AI_RESULTS_DIR, ensure_dirs

st.set_page_config(page_title="Lotes de IA · News Radar", page_icon="🤖", layout="wide")
sidebar_controls()
st.title("🤖 Lotes de IA")

# ── Cobertura de IA ───────────────────────────────────────────────────────────
try:
    cov = ai_coverage_stats()
    st.subheader("Cobertura de IA")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total artigos", cov["total"])
    c2.metric("Com IA", cov["with_ai"], f"{cov['pct_total']}%")
    c3.metric("Sem IA · score alto (≥60)", cov["high_no_ai"])
    c4.metric("Estimativa pós-lotes", f"{cov['projected_pct']}%",
              delta=f"+{cov['pending_articles']} arts pendentes")

    st.progress(cov["pct_total"] / 100,
                text=f"{cov['pct_total']}% cobertos — {cov['with_ai']}/{cov['total']}")

    col_b, col_p, col_t = st.columns(3)
    col_b.metric("Brasil", f"{cov['pct_brasil']}%",
                 f"{cov['ai_brasil']}/{cov['total_brasil']}")
    col_p.metric("Piauí", f"{cov['pct_piaui']}%",
                 f"{cov['ai_piaui']}/{cov['total_piaui']}")
    col_t.metric("Teresina", f"{cov['pct_teresina']}%",
                 f"{cov['ai_teresina']}/{cov['total_teresina']}")
except Exception as e:
    st.error(f"Erro cobertura: {e}")

st.divider()

# ── Gerador de lotes ──────────────────────────────────────────────────────────
st.subheader("📦 Gerar lote")

col_g1, col_g2, col_g3 = st.columns(3)
with col_g1:
    scope_gen = st.selectbox("Escopo", ["brasil", "piaui", "teresina"], key="lote_scope")
with col_g2:
    dias_opts = {"2h": 0.08, "6h": 0.25, "24h": 1, "3 dias": 3, "7 dias": 7}
    dias_label = st.selectbox("Período", list(dias_opts.keys()), index=2, key="lote_dias")
    days_back = dias_opts[dias_label]
with col_g3:
    batch_size = st.select_slider("Artigos por lote", [10, 20, 30, 50], value=30)

top_n = st.slider("Total de artigos para processar", 10, 300, 100, 10)

if st.button("⚡ Gerar lote agora", type="primary"):
    with st.spinner("Gerando..."):
        days_arg = max(1, int(days_back)) if days_back >= 1 else 1
        r = run_cli("make-ai-batches", "--scope", scope_gen,
                    "--top", str(top_n), "--batch-size", str(batch_size),
                    "--days-back", str(days_arg))
    if r["ok"]:
        st.success(f"✅ Lotes gerados! Veja abaixo.")
        st.rerun()
    else:
        st.error(r.get("error", "Erro"))

st.divider()

# ── Lotes pendentes ───────────────────────────────────────────────────────────
st.subheader("📋 Lotes pendentes")
st.info("**Fluxo:** Copie o prompt → cole em ChatGPT/Claude → copie a resposta JSON → cole abaixo → Importar")

def _validate(texto: str, batch: dict) -> dict:
    content = texto.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON inválido: {e}"}
    if isinstance(data, dict):
        data = data.get("items") or data.get("result") or data.get("noticias") or []
    if not isinstance(data, list) or not data:
        return {"ok": False, "error": "Resultado deve ser lista JSON não vazia."}

    result_ids = {str(item.get("id", "")) for item in data if isinstance(item, dict)}
    result_ids.discard("")

    expected_ids: set[str] = set()
    payload_path = Path(batch.get("payload_path", ""))
    if payload_path.exists():
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            expected_ids = {str(a.get("id", "")) for a in payload if isinstance(a, dict)}
            expected_ids.discard("")
        except Exception:
            pass

    matched = result_ids & expected_ids
    match_pct = round(len(matched) / len(expected_ids) * 100) if expected_ids else 0
    wrong = len(result_ids - expected_ids) > len(matched)

    return {
        "ok": True,
        "total_result": len(data),
        "total_expected": len(expected_ids),
        "matched": len(matched),
        "match_pct": match_pct,
        "wrong_batch": wrong,
    }

try:
    batches = list_ai_batches(limit=20)
except Exception as e:
    batches = []
    st.error(f"Erro: {e}")

pending = [b for b in batches if b["status"] == "pending"]
done = [b for b in batches if b["status"] == "completed"]
failed = [b for b in batches if b["status"] == "failed"]

if not pending:
    st.success("Nenhum lote pendente. Gere um novo lote acima.")
else:
    for batch in pending:
        age = ""
        if batch.get("created_at"):
            from datetime import datetime, timezone
            try:
                raw_created = batch["created_at"]
                if isinstance(raw_created, datetime):
                    created = raw_created
                else:
                    created = datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                else:
                    created = created.astimezone(timezone.utc)
                hours_ago = (datetime.now(timezone.utc) - created).total_seconds() / 3600
                age = f" · {hours_ago:.0f}h atrás"
            except Exception:
                pass

        with st.expander(
            f"🟡 {batch['batch_id']} — {batch['article_count']} artigos · {batch['scope']}{age}",
            expanded=True
        ):
            prompt_path = Path(batch.get("prompt_path", ""))
            if prompt_path.exists():
                prompt_text = prompt_path.read_text(encoding="utf-8")
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.text_area("Prompt para copiar", value=prompt_text, height=280,
                                 key=f"prompt_{batch['batch_id']}")
                with col_b:
                    st.markdown("**1.** Copie o prompt")
                    st.markdown("**2.** Cole no [ChatGPT](https://chat.openai.com) ou [Claude](https://claude.ai)")
                    st.markdown("**3.** Copie o JSON da resposta")
                    st.markdown("**4.** Cole abaixo e importe")
                    st.caption(f"IDs esperados: {batch['article_count']}")

                resultado = st.text_area("Cole a resposta JSON da IA",
                                          height=200,
                                          placeholder='[{"id": "...", "editoria": "...", ...}]',
                                          key=f"result_{batch['batch_id']}")
                validation = None
                if resultado.strip():
                    validation = _validate(resultado, batch)
                    if not validation["ok"]:
                        st.error(f"❌ {validation['error']}")
                    else:
                        pct = validation["match_pct"]
                        if validation["wrong_batch"]:
                            st.error(f"⚠️ Lote errado! Apenas {validation['matched']} IDs batem.")
                        elif pct >= 80:
                            st.success(f"✅ {validation['matched']}/{validation['total_expected']} artigos reconhecidos ({pct}%)")
                        elif pct >= 40:
                            st.warning(f"⚠️ Apenas {pct}% reconhecidos — verifique o prompt")
                        else:
                            st.error(f"❌ Muito poucos IDs reconhecidos ({pct}%) — lote errado?")

                can_import = (validation and validation.get("ok") and
                              not validation.get("wrong_batch") and
                              validation.get("match_pct", 0) >= 40)

                if st.button("✅ Importar resultado", key=f"import_{batch['batch_id']}",
                             disabled=not can_import):
                    try:
                        ensure_dirs()
                        result_path = AI_RESULTS_DIR / f"{batch['batch_id']}.result.json"
                        result_path.write_text(resultado.strip(), encoding="utf-8")
                        imported = import_ai_result_detailed(result_path, batch_id=batch["batch_id"])
                        st.success(f"✅ {imported['updated']} atualizados · {imported['ignored']} ignorados")
                        logs = imported.get("logs", [])
                        if logs:
                            with st.expander(f"📋 Log detalhado ({len(logs)} itens)", expanded=True):
                                for entry in logs:
                                    status = entry["status"]
                                    titulo = entry.get("titulo") or entry.get("id", "?")
                                    if status == "atualizado":
                                        st.markdown(f"✅ **{titulo[:70]}** · {entry.get('editoria','-')} · **{entry.get('prioridade','-')}** · IA {entry.get('ai_score','-')}")
                                        if entry.get("resumo"):
                                            st.caption(f"↳ {entry['resumo'][:120]}")
                                    elif status == "não encontrado":
                                        st.markdown(f"⚠️ ~~{entry.get('id','?')[:30]}~~ — _{entry.get('motivo','')}_ ")
                                    else:
                                        st.markdown(f"❌ {titulo[:70]} — `{entry.get('motivo','')[:80]}`")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao importar: {e}")
            else:
                st.error(f"Prompt não encontrado: {prompt_path}")

# ── Histórico ─────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Histórico")
col_d, col_f = st.columns(2)
with col_d:
    st.markdown(f"**✅ Concluídos:** {len(done)}")
    for b in done[:5]:
        st.caption(f"{b['batch_id'][:30]} · {b.get('imported_count',0)} importados")
with col_f:
    st.markdown(f"**❌ Falhados:** {len(failed)}")
    for b in failed[:5]:
        st.caption(f"{b['batch_id'][:30]} · {str(b.get('error',''))[:60]}")
