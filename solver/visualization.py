"""Figures and animations for atom transport and gate execution."""

from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter, writers
from matplotlib.colors import ListedColormap
from matplotlib.patches import Circle, Rectangle


def plot_atom_paths(maze, paths, targets=None, output_path="atom_paths.png"):
    """Draw a maze, atom paths, and optional groups of finish cells."""
    height, width = (len(maze), len(maze[0]))
    fig, ax = plt.subplots(figsize=(max(4, width), max(4, height)))
    ax.imshow(maze, cmap=ListedColormap(["white", "#404040"]), vmin=0, vmax=1)
    colors = plt.get_cmap("tab10")
    for i, path in enumerate(paths):
        xs, ys = zip(*path)
        color = colors(i % 10)
        ax.plot(xs, ys, "-o", color=color, linewidth=2, label=f"Atom {i}")
        ax.scatter(
            xs[0], ys[0], s=150, facecolors="none", edgecolors=color, linewidths=2
        )
        ax.scatter(xs[-1], ys[-1], s=170, marker="*", color=color, edgecolors="black")
        ax.annotate(
            f"S{i}",
            (xs[0], ys[0]),
            xytext=(5, 5),
            textcoords="offset points",
            color=color,
        )
        ax.annotate(
            f"F{i}",
            (xs[-1], ys[-1]),
            xytext=(5, 5),
            textcoords="offset points",
            color=color,
        )
    if targets is not None:
        finish_cells = sorted({cell for group in targets for cell in group})
        for index, (x, y) in enumerate(finish_cells):
            ax.add_patch(
                Rectangle(
                    (x - 0.5, y - 0.5),
                    1,
                    1,
                    fill=False,
                    edgecolor="green",
                    linewidth=2.5,
                    zorder=5,
                    label="Allowed target site" if index == 0 else None,
                )
            )
    ax.set_xticks(range(width))
    ax.set_yticks(range(height))
    ax.set_xticks([x - 0.5 for x in range(width + 1)], minor=True)
    ax.set_yticks([y - 0.5 for y in range(height + 1)], minor=True)
    ax.grid(which="minor", color="#aaaaaa", linewidth=1)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.set_xlim(-0.5, width - 0.5)
    ax.set_ylim(height - 0.5, -0.5)
    ax.set_aspect("equal")
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
    ax.set_title("Discrete atom transport paths")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, bbox_inches="tight")
    plt.close(fig)
    return destination


def animate_atom_paths(
    maze,
    paths,
    marked_cells=None,
    output_path="mapf_paths.mp4",
    fps=20,
    rows=None,
    columns=None,
    rydberg_layers=None,
    gate_layers=None,
    preview_path=None,
):
    """Save agent positions and optional active rows/columns at each step as MP4.

    marked_cells is a flat list of (x, y) cells outlined in green.
    rows[t] contains y coordinates; columns[t] contains x coordinates.
    rydberg_layers contains (step, pairs) for frames with a Rydberg pulse.
    gate_layers adds one display frame per gate event: green for global,
    blue cells for local targets, orange for CZ, preserving event order.
    """
    if not writers.is_available("ffmpeg"):
        raise RuntimeError("ffmpeg is required to save MP4 files.")
    if not paths or len({len(path) for path in paths}) != 1:
        raise ValueError("Provide nonempty paths of equal length.")
    frame_count = len(paths[0])
    rows = [[] for _ in range(frame_count)] if rows is None else rows
    columns = [[] for _ in range(frame_count)] if columns is None else columns
    if len(rows) != frame_count or len(columns) != frame_count:
        raise ValueError("Provide AOD row and column states for every transport step.")
    rydberg_steps = (
        {step for step, _ in rydberg_layers} if rydberg_layers is not None else set()
    )
    events_by_step = {}
    for event in gate_layers or []:
        step = event["step"]
        if not isinstance(step, int) or not 0 <= step < frame_count:
            raise ValueError("Gate steps must lie within the paths.")
        if event["type"] not in ("global", "local", "rydberg"):
            raise ValueError("Unknown gate layer type.")
        if event["type"] == "local" and any(
            (
                not isinstance(target, int) or not 0 <= target < len(paths)
                for target, rotation in event["gates"]
            )
        ):
            raise ValueError("A local gate references an unknown atom.")
        events_by_step.setdefault(step, []).append(event)
    display_frames = []
    for step in range(frame_count):
        display_frames.append((step, None))
        display_frames.extend(((step, event) for event in events_by_step.get(step, [])))
    height, width = (len(maze), len(maze[0]))
    fig, ax = plt.subplots(figsize=(max(4, width), max(4, height)))
    ax.imshow(maze, cmap=ListedColormap(["white", "#404040"]), vmin=0, vmax=1)
    ax.set_xticks(range(width))
    ax.set_yticks(range(height))
    ax.set_xticks([x - 0.5 for x in range(width + 1)], minor=True)
    ax.set_yticks([y - 0.5 for y in range(height + 1)], minor=True)
    ax.grid(which="minor", color="#aaaaaa", linewidth=1)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.set_xlim(-0.5, width - 0.5)
    ax.set_ylim(height - 0.5, -0.5)
    ax.set_aspect("equal")
    rydberg_overlay = Rectangle(
        (-0.5, -0.5),
        width,
        height,
        facecolor="orange",
        alpha=0.35,
        zorder=1,
        visible=False,
    )
    ax.add_patch(rydberg_overlay)
    global_gate_overlay = Rectangle(
        (-0.5, -0.5),
        width,
        height,
        facecolor="green",
        alpha=0.25,
        edgecolor="none",
        zorder=1,
        visible=False,
    )
    ax.add_patch(global_gate_overlay)
    local_gate_overlays = [
        Rectangle(
            (-0.5, -0.5),
            1,
            1,
            facecolor="blue",
            alpha=0.25,
            edgecolor="none",
            zorder=2,
            visible=False,
        )
        for _ in paths
    ]
    for overlay in local_gate_overlays:
        ax.add_patch(overlay)
    if marked_cells is not None:
        for x, y in dict.fromkeys(marked_cells):
            ax.add_patch(
                Rectangle(
                    (x - 0.5, y - 0.5),
                    1,
                    1,
                    fill=False,
                    edgecolor="green",
                    linewidth=2.5,
                    zorder=3,
                )
            )
    row_lines = [
        ax.axhline(0, color="red", linestyle="--", linewidth=2, zorder=3, visible=False)
        for _ in range(max(map(len, rows), default=0))
    ]
    column_lines = [
        ax.axvline(0, color="red", linestyle="--", linewidth=2, zorder=3, visible=False)
        for _ in range(max(map(len, columns), default=0))
    ]
    colors = plt.get_cmap("tab10")
    markers, labels = ([], [])
    for i, path in enumerate(paths):
        color = colors(i % 10)
        marker = Circle(path[0], radius=0.28, color=color, zorder=4)
        ax.add_patch(marker)
        label = ax.text(
            *path[0], str(i), color="white", ha="center", va="center", zorder=5
        )
        markers.append(marker)
        labels.append(label)

    def update(frame_index):
        t, event = display_frames[frame_index]
        rydberg_overlay.set_visible(
            event is not None
            and event["type"] == "rydberg"
            or (event is None and t in rydberg_steps)
        )
        global_gate_overlay.set_visible(event is not None and event["type"] == "global")
        local_targets = (
            {target for target, rotation in event["gates"]}
            if event is not None and event["type"] == "local"
            else set()
        )
        for atom, overlay in enumerate(local_gate_overlays):
            x, y = paths[atom][t]
            overlay.set_xy((x - 0.5, y - 0.5))
            overlay.set_visible(atom in local_targets)
        for line, y in zip(row_lines, rows[t]):
            line.set_ydata([y, y])
            line.set_visible(True)
        for line in row_lines[len(rows[t]) :]:
            line.set_visible(False)
        for line, x in zip(column_lines, columns[t]):
            line.set_xdata([x, x])
            line.set_visible(True)
        for line in column_lines[len(columns[t]) :]:
            line.set_visible(False)
        for path, marker, label in zip(paths, markers, labels):
            x, y = path[t]
            marker.center = (x, y)
            label.set_position((x, y))
        title = f"Atom transport: step {t}/{frame_count - 1}"
        if event is not None:
            detail = (
                "global"
                if event["type"] == "global"
                else (
                    "CZ"
                    if event["type"] == "rydberg"
                    else "local: " + ", ".join(map(str, sorted(local_targets)))
                )
            )
            gate_kind = "2q" if event["type"] == "rydberg" else "1q"
            title += f"\n{gate_kind} layer {event['layer']} | {detail}"
        ax.set_title(title)

    animation = FuncAnimation(
        fig, update, frames=len(display_frames), interval=1000 / fps
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    animation.save(str(destination), writer=FFMpegWriter(fps=fps))
    if preview_path is not None:
        preferred_type = (
            "rydberg"
            if any((event["type"] == "rydberg" for event in gate_layers or []))
            else None
        )
        preview_index = next(
            (
                index
                for index, (step, event) in enumerate(display_frames)
                if event is not None
                and (preferred_type is None or event["type"] == preferred_type)
            ),
            0,
        )
        update(preview_index)
        preview = Path(preview_path)
        preview.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(preview)
    plt.close(fig)
    print(f"Video saved: {destination.resolve()}")
    return destination
