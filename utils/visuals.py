"""Plotly figure builders + HTML helpers shared by the dashboard."""
import html
import re

import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from config import PHI_COLORS

PALETTE = ["#6c5ce7", "#00b4d8", "#06d6a0", "#ffb703", "#ef476f", "#ff7b00", "#8338ec", "#118ab2"]
SOURCE_COLORS = {"regex": "#8338ec", "spacy": "#00b4d8", "dictionary": "#06d6a0"}
STATUS_COLORS = {"PASS": "#06d6a0", "FAIL": "#ef476f"}


def _layout(fig, title=None, height=340):
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="#1b1b3a")) if title else None,
        height=height,
        margin=dict(l=20, r=20, t=50 if title else 20, b=70),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#33334d"),
        legend=dict(orientation="h", yanchor="top", y=-0.22, x=0, title=None),
    )
    return fig


# ----------------------------------------------------------- HTML helpers
def kpi(label, value, sub="", color="#6c5ce7", icon=""):
    return f"""
    <div class="kpi" style="--c:{color}">
      <div class="kpi-icon">{icon}</div>
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      <div class="kpi-sub">{sub}</div>
    </div>"""


def kpi_row(items):
    return '<div class="kpi-row">' + "".join(kpi(*i) for i in items) + "</div>"


def badge(text, color):
    return f'<span class="badge" style="background:{color}">{html.escape(str(text))}</span>'


def highlight_redacted(text):
    """Colour the [PLACEHOLDER] tokens in a redacted note."""
    safe = html.escape(text)

    def _sub(m):
        lab = m.group(1)
        c = PHI_COLORS.get(lab, "#6c5ce7")
        return f'<span class="ph" style="background:{c}">[{lab}]</span>'

    body = re.sub(r"\[([A-Z_]+)\]", _sub, safe)
    return f'<div class="note-box">{body}</div>'


def highlight_original(text, entities):
    """Mark the PHI spans (best effort - verbatim matches) in the raw note."""
    safe = html.escape(text)
    lookup = {}
    for e in entities:
        lookup.setdefault(html.escape(e["text"]), e["label"])
    if lookup:
        pat = re.compile("|".join(re.escape(k) for k in sorted(lookup, key=len, reverse=True)))

        def _sub(m):
            lab = lookup[m.group(0)]
            c = PHI_COLORS.get(lab, "#6c5ce7")
            return (f'<mark class="hl" style="background:{c}22;border-bottom:2px solid {c}"'
                    f' title="{lab}">{m.group(0)}</mark>')
        safe = pat.sub(_sub, safe)
    return f'<div class="note-box">{safe.replace(chr(10), "<br>")}</div>'


def legend_html():
    chips = "".join(f'<span class="ph" style="background:{c}">{k}</span>' for k, c in PHI_COLORS.items())
    return f'<div class="legend">{chips}</div>'


# ----------------------------------------------------------- figures
def donut_entities(breakdown, title="PHI entities by type"):
    labels = list(breakdown.keys())
    fig = go.Figure(go.Pie(
        labels=labels, values=[breakdown[k] for k in labels], hole=0.62,
        marker=dict(colors=[PHI_COLORS.get(k, "#999") for k in labels],
                    line=dict(color="white", width=2)),
        textinfo="label+value", sort=False))
    fig.add_annotation(text=f"<b>{sum(breakdown.values())}</b><br>entities",
                       showarrow=False, font=dict(size=18))
    return _layout(fig, title, 320)


def stage_impact(stages):
    names = [s["name"] for s in stages]
    vals = [s["info"].get("total", 0) if not s["info"].get("skipped") else 0 for s in stages]
    fig = go.Figure(go.Bar(
        x=vals, y=names, orientation="h",
        marker=dict(color=PALETTE[:len(names)]), text=vals, textposition="outside"))
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, "Changes made per pipeline stage", 320)


def stage_time(df):
    fig = px.bar(df, x="avg_ms", y="stage", orientation="h", color="avg_ms",
                 color_continuous_scale=["#caf0f8", "#6c5ce7"])
    fig.update_yaxes(autorange="reversed")
    fig.update_coloraxes(showscale=False)
    return _layout(fig, "Average latency per stage (ms)", 320)


def gauge(value, title, target=None, suffix="%", steps=(60, 90)):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, number=dict(suffix=suffix),
        title=dict(text=title, font=dict(size=15)),
        gauge=dict(
            axis=dict(range=[0, 100]),
            bar=dict(color="#6c5ce7"),
            steps=[dict(range=[0, steps[0]], color="#ffd6dd"),
                   dict(range=[steps[0], steps[1]], color="#fff1c9"),
                   dict(range=[steps[1], 100], color="#c9f5e5")],
            threshold=dict(line=dict(color="#1b1b3a", width=3), value=target) if target else None)))
    return _layout(fig, None, 270)


def status_pie(summary):
    counts = summary["status"].value_counts()
    fig = go.Figure(go.Pie(
        labels=counts.index, values=counts.values, hole=0.55,
        marker=dict(colors=[STATUS_COLORS.get(k, "#999") for k in counts.index],
                    line=dict(color="white", width=2))))
    return _layout(fig, "Verification outcome", 300)


def entities_stacked(entity_df):
    if entity_df.empty:
        return _layout(go.Figure(), "Entities per note", 320)
    g = entity_df.groupby(["note_id", "label"]).size().reset_index(name="count")
    g["note_id"] = g["note_id"].astype(str)
    fig = px.bar(g, x="note_id", y="count", color="label", color_discrete_map=PHI_COLORS)
    fig.update_xaxes(type="category", title="note")
    return _layout(fig, "PHI entities per note (by type)", 340)


def density_scatter(summary):
    s = summary.copy()
    s["note_id"] = s["note_id"].astype(str)
    fig = px.scatter(s, x="density_pct", y="utility_pct", size="entities", color="status",
                     symbol="scanned", hover_name="note_id", color_discrete_map=STATUS_COLORS,
                     labels={"density_pct": "Redaction density (% words)",
                             "utility_pct": "Text retained (%)"})
    fig.update_traces(marker=dict(line=dict(width=1, color="white")))
    return _layout(fig, "Redaction density vs. research utility", 340)


def recall_bar(recall_df, target):
    d = recall_df.copy()
    d["pct"] = 100 * d["recall"]
    fig = go.Figure(go.Bar(
        x=d["identifier"], y=d["pct"],
        marker=dict(color=["#06d6a0" if v >= 100 * target else "#ef476f" for v in d["pct"]]),
        text=[f"{v:.0f}% ({r}/{p})" for v, r, p in zip(d["pct"], d["removed"], d["present"])],
        textposition="outside"))
    fig.add_hline(y=100 * target, line_dash="dash", line_color="#1b1b3a",
                  annotation_text=f"target {100*target:.0f}%")
    fig.update_yaxes(range=[0, 118], title="identifiers removed (%)")
    return _layout(fig, "Recall by identifier type", 340)


def radar(recall_df):
    d = recall_df
    fig = go.Figure(go.Scatterpolar(
        r=list(100 * d["recall"]) + [100 * d["recall"].iloc[0]],
        theta=list(d["identifier"]) + [d["identifier"].iloc[0]],
        fill="toself", line=dict(color="#6c5ce7"), fillcolor="rgba(108,92,231,.25)"))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], showticklabels=True)))
    return _layout(fig, "Coverage radar", 340)


def leak_heatmap(matrix):
    cols = [c for c in matrix.columns if c != "note_id"]
    code = {"removed": 1, "LEAKED": 0, "n/a": np.nan}
    z = [[code[v] for v in row] for row in matrix[cols].values]
    text = matrix[cols].values
    fig = go.Figure(go.Heatmap(
        z=z, x=cols, y=[f"note {n}" for n in matrix["note_id"]], text=text,
        texttemplate="%{text}", colorscale=[[0, "#ef476f"], [1, "#06d6a0"]],
        showscale=False, xgap=3, ygap=3, zmin=0, zmax=1))
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, "Identifier removal matrix (green = removed, red = leaked, blank = not in note)", 340)


def source_sunburst(src_df):
    if src_df.empty:
        return _layout(go.Figure(), "Detector contribution", 340)
    g = src_df.groupby(["source", "label"]).size().reset_index(name="count")
    fig = px.sunburst(g, path=["source", "label"], values="count", color="source",
                      color_discrete_map=SOURCE_COLORS)
    return _layout(fig, "Which detector found what", 340)


def group_bars(group_df):
    m = group_df.melt(id_vars="group", value_vars=["pass_rate", "recall", "utility_pct"],
                      var_name="metric", value_name="value")
    m["metric"] = m["metric"].map({"pass_rate": "Verification pass %", "recall": "Identifier recall %",
                                   "utility_pct": "Text retained %"})
    fig = px.bar(m, x="metric", y="value", color="group", barmode="group",
                 color_discrete_sequence=["#00b4d8", "#ef476f"])
    fig.update_yaxes(range=[0, 110])
    return _layout(fig, "Scanned vs. natively-typed notes", 340)


def ablation_fig(abl):
    fig = go.Figure()
    fig.add_bar(x=abl["configuration"], y=abl["recall_pct"], name="Identifier recall %",
                marker_color="#6c5ce7")
    fig.add_bar(x=abl["configuration"], y=abl["residual_dates"], name="Residual date strings",
                marker_color="#ffb703", yaxis="y2")
    fig.update_layout(barmode="group",
                      yaxis=dict(title="recall %", range=[0, 110]),
                      yaxis2=dict(title="residual dates", overlaying="y", side="right", rangemode="tozero"))
    fig.update_xaxes(tickangle=-30)
    fig = _layout(fig, "Ablation - what each stage contributes", 470)
    fig.update_layout(legend=dict(orientation="h", y=1.12, x=0, yanchor="bottom"))
    return fig


def histogram(df, col, title, color="#6c5ce7"):
    fig = px.histogram(df, x=col, nbins=12, color_discrete_sequence=[color])
    return _layout(fig, title, 300)


def pie(series, title, colors=None):
    c = series.value_counts()
    fig = go.Figure(go.Pie(labels=c.index.astype(str), values=c.values, hole=0.5,
                           marker=dict(colors=colors or PALETTE, line=dict(color="white", width=2))))
    return _layout(fig, title, 300)


def bar(x, y, title, color="#00b4d8"):
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=color, text=y, textposition="outside"))
    return _layout(fig, title, 300)


def timeline(audit):
    d = audit.dropna(subset=["timestamp"]).copy()
    d["note_id"] = d["note_id"].astype(str)
    fig = px.scatter(d, x="timestamp", y="entities_found", color="verification_status",
                     color_discrete_map=STATUS_COLORS, hover_data=["note_id", "file_name"])
    fig.update_traces(marker=dict(size=11, line=dict(width=1, color="white")))
    return _layout(fig, "Processing timeline", 320)
