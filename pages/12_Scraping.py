"""
Scraping — Fase 10.1
Portais codificados em scraper/portals/ — não se adiciona pela UI.
Extração por período: since / until com parada automática por data.
"""
from __future__ import annotations
import sys
import time as _time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pandas as pd
import streamlit as st
from news_radar.dash_utils import sidebar_controls, fmt_dt
from news_radar.dashboard_queries import scraping_overview, scraping_recent_runs

st.set_page_config(page_title="Scraping · News Radar", page_icon="🕷️", layout="wide")
sidebar_controls()
st.title("🕷️ Scraping")

tab1, tab2, tab3 = st.tabs([
    "📊 Visão Geral",
    "▶ Execuções",
    "🏗️ Portais Codificados",
])


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 1 — Visão Geral
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    try:
        ov = scraping_overview()
    except Exception as exc:
        st.error(f"Erro: {exc}")
        ov = {}

    try:
        from news_radar.scraper.portals import PORTAL_SCRAPERS
        n_coded = len(PORTAL_SCRAPERS)
    except Exception:
        n_coded = 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Portais codificados", n_coded)
    c2.metric("Execuções registradas", ov.get("runs_total", 0))
    c3.metric("Taxa de sucesso", f"{ov.get('success_rate', 0.0):.1f}%")
    last = ov.get("last_run_at")
    c4.metric("Última execução", fmt_dt(last, 16) if last else "—")

    if n_coded > 0:
        rows = [{"Portal": name, "Escopo": s.scope, "Trust": f"{s.trust}/5",
                 "Analisado": s.last_analyzed, "Data na URL": "✅" if hasattr(s, "extract_date_from_url") and
                 s.extract_date_from_url("test/2026/05/29/x") is not None else "—"}
                for name, s in PORTAL_SCRAPERS.items()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.subheader("Execuções recentes")
    try:
        runs = scraping_recent_runs(limit=15)
    except Exception:
        runs = []
    if runs:
        df = pd.DataFrame(runs)
        cols = [c for c in ["id", "source_name", "strategy", "status",
                             "found_count", "inserted_count", "error_count", "started_at"] if c in df.columns]
        if "started_at" in df.columns:
            df["started_at"] = df["started_at"].apply(lambda v: fmt_dt(v, 16))
        st.dataframe(df[cols], use_container_width=True, height=280)
    else:
        st.info("Nenhuma execução registrada ainda.")


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 2 — Execuções
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Histórico de Execuções")
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        filter_status = st.selectbox("Status", ["todos", "ok", "error", "running"], key="runs_status")
    with col_r2:
        runs_limit = st.slider("Quantidade", 10, 200, 50, key="runs_limit")

    try:
        runs_all = scraping_recent_runs(
            limit=runs_limit,
            status=None if filter_status == "todos" else filter_status,
        )
    except Exception as exc:
        st.error(f"Erro: {exc}")
        runs_all = []

    for run in runs_all:
        icon = "✅" if run.get("status") == "ok" else ("❌" if run.get("status") == "error" else "⏳")
        label = (f"{icon} #{run['id']} · {run.get('source_name','?')} · "
                 f"{run.get('strategy','?')} · {fmt_dt(run.get('started_at'), 16)}")
        with st.expander(label):
            cols = st.columns(4)
            cols[0].metric("Encontradas", run.get("found_count", 0))
            cols[1].metric("Inseridas", run.get("inserted_count", 0))
            cols[2].metric("Atualizadas", run.get("updated_count", 0))
            cols[3].metric("Erros", run.get("error_count", 0))
            if run.get("error_message"):
                st.warning(f"Erro: {run['error_message']}")
    if not runs_all:
        st.info("Nenhuma execução encontrada.")


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 3 — Portais Codificados
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Portais Codificados")

    try:
        from news_radar.scraper.portals import PORTAL_SCRAPERS
    except Exception as exc:
        st.error(f"Erro ao carregar portais: {exc}")
        PORTAL_SCRAPERS = {}

    if not PORTAL_SCRAPERS:
        st.info("Nenhum portal registrado.")
        st.stop()

    portal_names = list(PORTAL_SCRAPERS.keys())

    # ── Seleção de portais ─────────────────────────────────────────────────────
    selected_portals = st.multiselect(
        "Portais", portal_names, default=portal_names[:1], key="selected_portals"
    )
    if not selected_portals:
        st.info("Selecione ao menos um portal.")
        st.stop()

    st.divider()

    # ── Período ───────────────────────────────────────────────────────────────
    st.markdown("**Período de captura**")

    shortcut = st.radio(
        "Atalho",
        ["Hoje", "Ontem", "Últimos 3 dias", "Últimos 7 dias", "Personalizado"],
        horizontal=True,
        key="period_shortcut",
    )
    today = date.today()
    if shortcut == "Hoje":
        date_since, date_until = today, today
    elif shortcut == "Ontem":
        date_since, date_until = today - timedelta(days=1), today - timedelta(days=1)
    elif shortcut == "Últimos 3 dias":
        date_since, date_until = today - timedelta(days=2), today
    elif shortcut == "Últimos 7 dias":
        date_since, date_until = today - timedelta(days=6), today
    else:
        col_d1, col_d2 = st.columns(2)
        date_since = col_d1.date_input("De", value=today - timedelta(days=1), key="date_since")
        date_until = col_d2.date_input("Até", value=today, key="date_until")

    since_dt = datetime(date_since.year, date_since.month, date_since.day, tzinfo=timezone.utc)
    until_dt = datetime(date_until.year, date_until.month, date_until.day,
                        23, 59, 59, tzinfo=timezone.utc)

    st.caption(
        f"📅 {date_since.strftime('%d/%m/%Y')} → {date_until.strftime('%d/%m/%Y')} "
        f"({(date_until - date_since).days + 1} dia(s))"
    )

    st.divider()

    # ── Velocidade ────────────────────────────────────────────────────────────
    st.markdown("**Velocidade de extração**")
    rate_limit = st.slider(
        "Pausa entre artigos (segundos)",
        min_value=0.5, max_value=5.0, value=1.5, step=0.5,
        key="rate_limit_slider",
        help="Menor = mais rápido. Respeite o portal: não use 0 em produção.",
    )
    st.caption(
        f"{'🟢 Rápido' if rate_limit <= 1.0 else '🟡 Moderado' if rate_limit <= 2.5 else '🔵 Conservador'} "
        f"— aprox. {rate_limit:.1f}s por artigo"
    )

    st.divider()

    # ── Botão de busca ────────────────────────────────────────────────────────
    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn2:
        btn_fetch = st.button("🔍 Buscar URLs", use_container_width=True, key="btn_fetch_urls",
                              type="primary")

    urls_key = "portal_multi_urls"
    if btn_fetch:
        st.session_state.pop("portal_multi_articles", None)
        st.session_state.pop("portal_multi_inserted", None)
        all_found: dict[str, list[str]] = {}
        all_debug: dict[str, dict] = {}
        prog = st.progress(0)
        for pi, pname in enumerate(selected_portals):
            scraper = PORTAL_SCRAPERS[pname]
            has_url_date = scraper.extract_date_from_url("https://x/2000/1/1/x") is not None
            prog.progress((pi + 0.3) / len(selected_portals), text=f"Buscando {pname}…")
            found: list[str] = []
            seen: set[str] = set()
            n_too_new = n_too_old = n_no_date = 0
            stopped_reason = "fim das páginas"
            try:
                for page in range(1, scraper.pagination_max + 1):
                    page_urls = scraper.fetch_listing_urls(page=page)
                    if not page_urls:
                        break
                    new = [u for u in page_urls if u not in seen]
                    seen.update(new)

                    page_hit_floor = False  # encontrou artigo mais velho que since
                    for u in new:
                        url_date = scraper.extract_date_from_url(u)
                        if url_date is not None:
                            # Portal com data na URL — filtra antes de baixar
                            if url_date > until_dt:
                                n_too_new += 1
                                continue  # mais recente que o período — pula, mas continua paginando
                            if url_date < since_dt:
                                n_too_old += 1
                                page_hit_floor = True  # artigos estão ficando velhos demais
                                continue
                            found.append(u)  # dentro do período
                        else:
                            # Sem data na URL — inclui tudo, filtra após extração
                            n_no_date += 1
                            found.append(u)

                    # Só para de paginar quando encontra artigos MAIS VELHOS que since
                    # (não para quando encontra artigos mais recentes que until)
                    if page_hit_floor:
                        stopped_reason = f"artigos mais antigos que {date_since.strftime('%d/%m')}"
                        break
            except Exception as exc:
                st.warning(f"⚠️ {pname}: {str(exc)[:80]}")

            all_found[pname] = found
            all_debug[pname] = {
                "has_url_date": has_url_date,
                "too_new": n_too_new,
                "too_old": n_too_old,
                "no_date": n_no_date,
                "found": len(found),
                "stopped": stopped_reason,
            }
            prog.progress((pi + 1) / len(selected_portals))
        prog.empty()
        st.session_state[urls_key] = all_found
        st.session_state["portal_debug"] = all_debug
        total = sum(len(v) for v in all_found.values())
        st.success(f"✅ {total} URLs no período em {len(selected_portals)} portal(is)")

        # Mostra resumo de filtro por portal
        for pname, dbg in all_debug.items():
            mode = "📍 data na URL" if dbg["has_url_date"] else "📄 sem data na URL (filtra após extrair)"
            st.caption(
                f"**{pname}** [{mode}] — "
                f"encontradas: {dbg['found']} · "
                f"muito recentes: {dbg['too_new']} · "
                f"muito antigas: {dbg['too_old']} · "
                f"parou: {dbg['stopped']}"
            )

    # ── Dedup + extração ──────────────────────────────────────────────────────
    if urls_key in st.session_state:
        all_found = st.session_state[urls_key]

        try:
            from news_radar.scraper.runs import get_known_urls
            known = get_known_urls(None)
        except Exception:
            known = set()

        url_rows = [{"portal": p, "url": u, "nova": u not in known}
                    for p, urls in all_found.items() for u in urls]
        url_df = pd.DataFrame(url_rows) if url_rows else pd.DataFrame()

        if url_df.empty:
            st.info("Nenhuma URL encontrada no período.")
        else:
            n_total = len(url_df)
            n_new = int(url_df["nova"].sum())
            n_known_c = n_total - n_new

            ck1, ck2, ck3 = st.columns(3)
            ck1.metric("No período", n_total)
            ck2.metric("✅ Já conhecidas", n_known_c)
            ck3.metric("🆕 Novas", n_new)

            # Resumo por portal
            portal_counts = (url_df.groupby("portal")["nova"]
                             .agg(total="count", novas="sum")
                             .reset_index())
            portal_counts.columns = ["Portal", "Total", "Novas"]
            st.dataframe(portal_counts, use_container_width=True, hide_index=True)

            col_ex1, col_ex2 = st.columns([3, 1])
            with col_ex1:
                skip_known = st.checkbox("Pular já conhecidas", value=True, key="skip_known_ui")
            with col_ex2:
                urls_to_extract = url_df[url_df["nova"]].to_dict("records") if skip_known else url_df.to_dict("records")
                btn_extract = st.button(
                    f"▶ Extrair {len(urls_to_extract)} artigos",
                    use_container_width=True, key="btn_extract", type="primary",
                    disabled=len(urls_to_extract) == 0,
                )

        # ── Extração com progresso ─────────────────────────────────────────────
        art_key = "portal_multi_articles"
        if "btn_extract" in dir() and btn_extract and urls_to_extract:
            st.session_state.pop("portal_multi_inserted", None)
            total_ex = len(urls_to_extract)
            progress_bar = st.progress(0, text="Iniciando…")
            log_slot = st.empty()
            extracted: list[dict] = []

            for i, row in enumerate(urls_to_extract):
                pname = row["portal"]
                url = row["url"]
                scraper = PORTAL_SCRAPERS[pname]
                short = url.split("/")[-1][:50]
                progress_bar.progress(
                    (i + 1) / total_ex,
                    text=f"[{i+1}/{total_ex}] {pname} · {short}",
                )
                log_slot.code(
                    f"[{i+1}/{total_ex}] [{pname}] {url}\n"
                    + "\n".join(
                        f"  ✅ {a['title'][:55]}" if a["ok"] else f"  ❌ {a.get('error','')[:50]}"
                        for a in extracted[-4:]
                    ),
                    language=None,
                )
                _time.sleep(rate_limit)
                try:
                    art = scraper.scrape_article(url)
                    extracted.append({
                        "portal": pname, "url": art.url, "ok": art.ok,
                        "title": art.title or "", "author": art.author or "",
                        "date": art.date_str or "", "chars": len(art.content or ""),
                        "quality": art.extraction_quality,
                        "error": art.error or "", "content": art.content or "",
                    })
                except Exception as exc:
                    extracted.append({"portal": pname, "url": url, "ok": False,
                                      "title": "", "date": "", "chars": 0, "quality": 0,
                                      "error": str(exc)[:120], "content": "", "author": ""})

            progress_bar.empty()
            log_slot.empty()
            st.session_state[art_key] = extracted

        # ── Resultados + Timeline ──────────────────────────────────────────────
        if art_key in st.session_state:
            articles = st.session_state[art_key]
            ok_arts = [a for a in articles if a["ok"]]

            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Extraídos OK", f"{len(ok_arts)}/{len(articles)}")
            m2.metric("Erros", len(articles) - len(ok_arts))
            avg_q = sum(a["quality"] for a in ok_arts) / max(len(ok_arts), 1)
            m3.metric("Qualidade média", f"{avg_q:.2f}")
            avg_c = sum(a["chars"] for a in ok_arts) / max(len(ok_arts), 1)
            m4.metric("Chars médio", f"{int(avg_c)}")

            # ── Relatório de Cobertura ─────────────────────────────────────────
            import re as _re
            from datetime import date as _date

            st.subheader("🔍 Relatório de Cobertura")

            # Monta todos os dias do período
            period_days = [
                date_since + timedelta(days=i)
                for i in range((date_until - date_since).days + 1)
            ]

            # Parseia data de cada artigo extraído
            def _parse_day(date_raw: str) -> str | None:
                if not date_raw:
                    return None
                m = _re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", date_raw)
                if m:
                    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                m2 = _re.search(r"(\d{2})/(\d{2})/(\d{4})", date_raw)
                if m2:
                    return f"{m2.group(3)}-{m2.group(2)}-{m2.group(1)}"
                return None

            # Conta artigos por portal × dia
            from collections import defaultdict
            coverage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            no_date_count: dict[str, int] = defaultdict(int)
            for a in ok_arts:
                day = _parse_day(a.get("date", ""))
                if day:
                    coverage[a["portal"]][day] += 1
                else:
                    no_date_count[a["portal"]] += 1

            # Matriz de cobertura
            day_labels = [d.strftime("%d/%m") for d in period_days]
            day_keys = [d.strftime("%Y-%m-%d") for d in period_days]

            matrix_rows = []
            warnings: list[str] = []

            for pname in selected_portals:
                row = {"Portal": pname}
                portal_total = 0
                zero_days = []
                for dk, dl in zip(day_keys, day_labels):
                    cnt = coverage[pname].get(dk, 0)
                    row[dl] = cnt
                    portal_total += cnt
                    if cnt == 0:
                        zero_days.append(dl)

                # Status de paginação
                dbg = st.session_state.get("portal_debug", {}).get(pname, {})
                stopped = dbg.get("stopped", "")
                hit_floor = "artigos mais antigos" in stopped
                page_limit = not hit_floor and dbg.get("has_url_date", False)

                no_date = no_date_count.get(pname, 0)
                status = "✅" if hit_floor or not dbg.get("has_url_date") else "⚠️"
                row["Total"] = portal_total
                row["Cobertura"] = (
                    f"{status} completa" if hit_floor or not dbg.get("has_url_date")
                    else f"⚠️ limite de pgs"
                )
                if no_date > 0:
                    row["Sem data"] = no_date
                matrix_rows.append(row)

                # Alertas
                if page_limit:
                    warnings.append(
                        f"⚠️ **{pname}**: atingiu limite de páginas sem chegar ao floor — "
                        f"pode haver artigos de {date_since.strftime('%d/%m')} não capturados. "
                        f"Aumente 'Máx. páginas' ou verifique paginação do portal."
                    )
                if zero_days and portal_total > 0:
                    warnings.append(
                        f"🕳️ **{pname}**: dias sem artigos — {', '.join(zero_days)}"
                    )
                if portal_total == 0:
                    warnings.append(
                        f"❌ **{pname}**: nenhum artigo extraído no período. "
                        f"Verifique se o portal tem cobertura nessa data."
                    )

            if matrix_rows:
                # Exibe matriz
                mat_df = pd.DataFrame(matrix_rows)
                # Coluna de cobertura no final
                fixed_cols = ["Portal", "Total", "Cobertura"]
                day_cols = day_labels
                cols_order = fixed_cols + day_cols + (["Sem data"] if "Sem data" in mat_df.columns else [])
                mat_df = mat_df[[c for c in cols_order if c in mat_df.columns]]

                col_cfg = {
                    dl: st.column_config.NumberColumn(dl, min_value=0)
                    for dl in day_labels if dl in mat_df.columns
                }
                col_cfg["Total"] = st.column_config.NumberColumn("Total", min_value=0)
                st.dataframe(mat_df, use_container_width=True, hide_index=True,
                             column_config=col_cfg)

            # Avisos e alertas
            if warnings:
                st.markdown("**Alertas de cobertura:**")
                for w in warnings:
                    st.warning(w)
            else:
                st.success(
                    f"✅ Cobertura completa: todos os portais cobriram o período "
                    f"{date_since.strftime('%d/%m')}→{date_until.strftime('%d/%m')} sem lacunas detectadas."
                )

            # Totais globais por dia (gap detection)
            total_by_day = {dk: sum(coverage[p].get(dk, 0) for p in selected_portals)
                            for dk in day_keys}
            zero_global = [day_labels[i] for i, dk in enumerate(day_keys) if total_by_day[dk] == 0]
            if zero_global:
                st.error(
                    f"🕳️ **Gap total** — dias sem NENHUM artigo em nenhum portal: "
                    f"{', '.join(zero_global)}. "
                    "Isso pode indicar problema de conectividade ou período sem cobertura."
                )

            st.divider()

            # Timeline
            tl_rows = []
            for a in ok_arts:
                date_raw = a.get("date", "")
                m = _re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", date_raw)
                if not m:
                    m2r = _re.search(r"(\d{2})/(\d{2})/(\d{4})", date_raw)
                    date_sort = f"{m2r.group(3)}-{m2r.group(2)}-{m2r.group(1)}" if m2r else "0000-00-00"
                else:
                    date_sort = m.group(1).replace("/", "-")
                tl_rows.append({
                    "Portal": a["portal"],
                    "Título": a["title"][:70],
                    "Data": (date_raw[:16] if date_raw else "—"),
                    "_sort": date_sort,
                    "Qualidade": a["quality"],
                    "Chars": a["chars"],
                    "URL": a["url"],
                })

            if tl_rows:
                tl_df = (pd.DataFrame(tl_rows)
                         .sort_values("_sort", ascending=False)
                         .drop(columns=["_sort"]))
                st.subheader("📅 Timeline")
                st.dataframe(
                    tl_df, use_container_width=True, height=380,
                    column_config={
                        "Qualidade": st.column_config.ProgressColumn("Qualidade", min_value=0, max_value=1, format="%.2f"),
                        "Chars": st.column_config.NumberColumn("Chars"),
                        "URL": st.column_config.LinkColumn("URL"),
                    },
                )

                # Gráficos
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.subheader("Por portal")
                    counts = (pd.DataFrame(articles)
                              .groupby("portal")
                              .agg(total=("ok", "count"), ok=("ok", "sum"))
                              .rename(columns={"total": "Total", "ok": "OK"}))
                    st.bar_chart(counts, use_container_width=True)
                with col_g2:
                    date_counts = (pd.DataFrame(tl_rows)[["Portal", "Data"]]
                                   .groupby("Data").size().reset_index(name="Artigos"))
                    if not date_counts.empty:
                        st.subheader("Por data")
                        st.bar_chart(date_counts.set_index("Data"), use_container_width=True)

            # Detalhe
            if articles:
                titles_sel = [f"[{a['portal']}] {a['title'][:65] or a['url']}" for a in articles]
                sel_idx = st.selectbox("Ver artigo", range(len(titles_sel)),
                                       format_func=lambda i: titles_sel[i], key="art_detail")
                sel = articles[sel_idx]
                if sel["content"]:
                    st.text_area("Texto", sel["content"][:2000], height=160,
                                 key="art_text_detail", disabled=True)

            st.divider()

            # Inserção
            ins_key = "portal_multi_inserted"
            if st.session_state.get(ins_key):
                st.success("✅ Inserido nesta sessão.")
            else:
                col_ins1, col_ins2 = st.columns([1, 3])
                with col_ins1:
                    only_ok = st.checkbox("Só artigos OK", value=True, key="portal_only_ok")
                with col_ins2:
                    if st.button("💾 Inserir no banco", type="primary", key="btn_insert_db"):
                        from news_radar.scraper.runs import (create_scrape_run,
                                                              finish_scrape_run, insert_scraped_page)
                        from news_radar.scraper.models import ScrapeRunStats
                        to_insert = [a for a in articles if a["ok"]] if only_ok else articles
                        with st.spinner(f"Inserindo {len(to_insert)} artigos…"):
                            run_id = create_scrape_run(None, "portal_coded")
                            stats = ScrapeRunStats(found=len(articles))
                            for a in to_insert:
                                try:
                                    insert_scraped_page(
                                        source_id=None, run_id=run_id,
                                        url=a["url"],
                                        extraction_status="ok" if a["ok"] else "error",
                                        title=a["title"] or None,
                                        error_message=a["error"] or None,
                                    )
                                    stats.inserted += 1
                                except Exception:
                                    stats.errors += 1
                            finish_scrape_run(run_id, stats)
                        st.session_state[ins_key] = True
                        st.success(f"✅ {stats.inserted} artigos inseridos (run_id={run_id})")
                        st.rerun()

            if st.session_state.get(ins_key):
                col_rk1, col_rk2 = st.columns([3, 1])
                with col_rk2:
                    if st.button("📊 Recalcular ranking", use_container_width=True, key="btn_rank"):
                        from news_radar.dash_utils import run_cli
                        with st.spinner("Ranqueando…"):
                            r = run_cli("rank", timeout=120)
                        if r["ok"]:
                            st.success(str(r.get("output", "Ranking recalculado.")))
                        else:
                            st.error(str(r.get("error", "Erro")))
