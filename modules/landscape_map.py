"""PCA projection and K-Means groups for exploration, not legal classification."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from modules.models import AnalysisResult


def build_landscape(result: AnalysisResult) -> go.Figure:
    fig = go.Figure()
    if len(result.matches) < 2:
        fig.add_annotation(text="至少需要两条检索记录才能绘制景观图。", showarrow=False)
        return fig
    vectors = result.vectors
    if vectors.ndim != 2 or vectors.shape[0] != len(result.matches) + 1:
        raise ValueError("景观图与相似度结果未对齐。")
    dimensions = min(2, vectors.shape[0], vectors.shape[1])
    coords = PCA(n_components=dimensions, random_state=42).fit_transform(vectors)
    if dimensions == 1:
        coords = np.column_stack((coords[:, 0], np.zeros(len(coords))))
    record_coords = coords[1:]
    unique_points = len(np.unique(record_coords.round(8), axis=0))
    groups = min(3, len(result.matches), unique_points)
    labels = (
        KMeans(n_clusters=groups, n_init=10, random_state=42).fit_predict(record_coords)
        if groups > 1
        else np.zeros(len(result.matches), dtype=int)
    )
    for group in sorted(set(labels)):
        indexes = np.flatnonzero(labels == group)
        fig.add_trace(go.Scatter(
            x=record_coords[indexes, 0],
            y=record_coords[indexes, 1],
            mode="markers",
            name=f"聚类 {int(group) + 1}",
            marker={"size": 11},
            text=[result.matches[int(i)].record.title for i in indexes],
            customdata=[[result.matches[int(i)].similarity] for i in indexes],
            hovertemplate="%{text}<br>相似度参考：%{customdata[0]:.1%}<extra></extra>",
        ))
    fig.add_trace(go.Scatter(
        x=[coords[0, 0]], y=[coords[0, 1]], mode="markers", name="发明/检索词",
        marker={"symbol": "star", "size": 17, "color": "red"},
    ))
    fig.update_layout(
        title="检索结果景观图（PCA + K-Means）",
        xaxis_title="主成分 1", yaxis_title="主成分 2", height=420,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )
    return fig
