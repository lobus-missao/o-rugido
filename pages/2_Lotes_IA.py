"""Aba Lotes de IA — fluxo manual de análise."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, run_cli, fmt_dt
from news_radar.dashboard_queries import ai_coverage_stats
from news_radar.ai_batches import (
    list_ai_batches,
    import_ai_result_detailed,
    validate_ai_response,
    get_ai_batch,
)
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
        st.success("✅ Lotes gerados! Veja abaixo.")
        st.rerun()
    else:
        st.error(r.get("error", "Erro"))

st.divider()

# ── Lotes pendentes ───────────────────────────────────────────────────────────
st.subheader("📋 Lotes pendentes")
st.info(
    "**Fluxo:** Copie o prompt → cole em ChatGPT/Claude → copie a resposta JSON → cole abaixo → Importar"
)

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
                    # st.code oferece botão de cópia nativo do Streamlit
                    st.caption("📋 Prompt — use o botão de cópia no canto superior direito do bloco:")
                    st.code(prompt_text, language=None)

                with col_b:
                    st.markdown("**Como usar:**")
                    st.markdown("**1.** Copie o prompt acima")
                    st.markdown("**2.** Cole no [ChatGPT](https://chat.openai.com) ou [Claude](https://claude.ai)")
                    st.markdown("**3.** Copie a resposta JSON")
                    st.markdown("**4.** Cole abaixo e clique em Importar")
                    st.divider()
                    st.caption(f"Artigos no lote: **{batch['article_count']}**")
                    st.caption(f"Escopo: **{batch['scope']}**")

                    # Métricas do prompt
                    try:
                        from news_radar.ai_batches import estimate_text_metrics
                        m = estimate_text_metrics(prompt_text)
                        st.caption(f"≈ {m['estimated_tokens']:,} tokens")
                        st.caption(f"≈ {m['estimated_words']:,} palavras")
                    except Exception:
                        pass

                # Carrega IDs esperados do payload
                expected_ids: set[str] = set()
                payload_path = Path(batch.get("payload_path", ""))
                if payload_path.exists():
                    try:
                        payload = json.loads(payload_path.read_text(encoding="utf-8"))
                        expected_ids = {
                            str(a.get("id", "")) for a in payload
                            if isinstance(a, dict) and a.get("id")
                        }
                    except Exception:
                        pass

                resultado = st.text_area(
                    "Cole a resposta JSON da IA",
                    height=220,
                    placeholder='[{"id": "...", "editoria": "...", "prioridade": "...", ...}]',
                    key=f"result_{batch['batch_id']}",
                )

                validation = None
                if resultado.strip():
                    validation = validate_ai_response(resultado, expected_ids)

                    if not validation["ok"]:
                        st.error(f"❌ {validation['error']}")
                    else:
                        pct = validation["match_pct"]
                        if validation["wrong_batch"]:
                            st.error(
                                f"⚠️ Lote errado — apenas {validation['matched']} de "
                                f"{validation['total_expected']} IDs reconhecidos. "
                                "Verifique se copiou a resposta do lote correto."
                            )
                        elif pct >= 80:
                            st.success(
                                f"✅ {validation['matched']}/{validation['total_expected']} "
                                f"artigos reconhecidos ({pct}%)"
                            )
                        elif pct >= 40:
                            st.warning(
                                f"⚠️ {pct}% dos artigos reconhecidos "
                                f"({validation['matched']}/{validation['total_expected']}) — "
                                "importação permitida, mas verifique o prompt."
                            )
                        else:
                            st.error(
                                f"❌ Apenas {pct}% dos IDs reconhecidos "
                                f"({validation['matched']}/{validation['total_expected']}). "
                                "Threshold mínimo: 40%."
                            )

                        # Erros de campos
                        if validation.get("item_errors"):
                            with st.expander(
                                f"⚠️ {len(validation['item_errors'])} aviso(s) de campos", expanded=False
                            ):
                                for err in validation["item_errors"][:20]:
                                    st.caption(f"• {err}")

                can_import = (
                    validation is not None
                    and validation.get("ok")
                    and validation.get("can_import")
                )

                if st.button(
                    "✅ Importar resultado",
                    key=f"import_{batch['batch_id']}",
                    disabled=not can_import,
                    type="primary",
                ):
                    try:
                        ensure_dirs()
                        result_path = AI_RESULTS_DIR / f"{batch['batch_id']}.result.json"
                        result_path.write_text(resultado.strip(), encoding="utf-8")
                        imported = import_ai_result_detailed(
                            result_path,
                            batch_id=batch["batch_id"],
                            actor="Editor",
                        )
                        st.success(
                            f"✅ **{imported['updated']}** artigos atualizados · "
                            f"**{imported['ignored']}** ignorados"
                        )
                        logs = imported.get("logs", [])
                        if logs:
                            with st.expander(
                                f"📋 Log detalhado ({len(logs)} itens)", expanded=True
                            ):
                                for entry in logs:
                                    status = entry["status"]
                                    titulo = entry.get("titulo") or entry.get("id", "?")
                                    if status == "atualizado":
                                        st.markdown(
                                            f"✅ **{titulo[:70]}** · "
                                            f"{entry.get('editoria', '-')} · "
                                            f"**{entry.get('prioridade', '-')}** · "
                                            f"IA {entry.get('ai_score', '-')}"
                                        )
                                        if entry.get("resumo"):
                                            st.caption(f"↳ {entry['resumo'][:120]}")
                                        if entry.get("justificativa"):
                                            st.caption(f"💡 {entry['justificativa'][:100]}")
                                    elif status == "não encontrado":
                                        st.markdown(
                                            f"⚠️ ~~{entry.get('id', '?')[:30]}~~ — "
                                            f"_{entry.get('motivo', '')}_"
                                        )
                                    else:
                                        st.markdown(
                                            f"❌ {titulo[:70]} — "
                                            f"`{entry.get('motivo', '')[:80]}`"
                                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao importar: {e}")
            else:
                st.error(f"Prompt não encontrado: {prompt_path}")

# ── Histórico e Reimportação ──────────────────────────────────────────────────
st.divider()
st.subheader("Histórico")

col_d, col_f = st.columns(2)
with col_d:
    st.markdown(f"**✅ Concluídos:** {len(done)}")
    for b in done[:8]:
        imported_n = b.get("imported_count", 0)
        ignored_n = b.get("ignored_count", 0)
        created = fmt_dt(b.get("created_at"), 16)
        with st.expander(
            f"✅ {b['batch_id'][:35]} · {imported_n} importados · {created}", expanded=False
        ):
            st.caption(f"Escopo: {b['scope']} · {b['article_count']} artigos no lote")
            st.caption(f"Importados: {imported_n} · Ignorados: {ignored_n}")

            # Botão de reimportação
            result_path = Path(b.get("result_path") or "")
            payload_path_done = Path(b.get("payload_path") or "")
            if result_path.exists():
                reimp_key = f"reimp_{b['batch_id']}"
                if st.button("🔄 Reimportar", key=reimp_key, type="secondary"):
                    exp_ids: set[str] = set()
                    if payload_path_done.exists():
                        try:
                            pl = json.loads(payload_path_done.read_text(encoding="utf-8"))
                            exp_ids = {str(a.get("id", "")) for a in pl if isinstance(a, dict)}
                        except Exception:
                            pass
                    content = result_path.read_text(encoding="utf-8")
                    val = validate_ai_response(content, exp_ids)
                    if val.get("ok") and val.get("can_import"):
                        try:
                            res = import_ai_result_detailed(
                                result_path, batch_id=None, actor="Editor"
                            )
                            st.success(f"✅ Reimportado: {res['updated']} atualizados")
                        except Exception as re_exc:
                            st.error(f"Erro ao reimportar: {re_exc}")
                    else:
                        st.error(val.get("error") or "Resultado inválido para reimportação.")
            else:
                st.caption("Arquivo de resultado não encontrado.")

with col_f:
    st.markdown(f"**❌ Falhados:** {len(failed)}")
    for b in failed[:5]:
        st.caption(f"{b['batch_id'][:30]} · {str(b.get('error', ''))[:60]}")
