import { RichText } from "./RichText";
import { BoardMark } from "./BoardMark";
import {
  BoardCoordinatePlane,
  BoardFractionBars,
  BoardGeometryFigure,
  BoardNumberLine,
} from "./BoardFigures";
import type {
  BoardBlock as Block,
  BoardCalloutBlock,
  BoardExpressionCompareBlock,
  BoardStepsBlock,
} from "../types";

/** Board math arrives as bare LaTeX; RichText expects delimiters. */
export function Math({ latex, className }: { latex: string; className?: string }) {
  return <RichText content={`$${latex}$`} className={className ?? "board-math"} />;
}

const CALLOUT_ICON = {
  insight: "lightbulb",
  warning: "warning",
  common_mistake: "error",
} as const;

function Steps({ block, active }: { block: BoardStepsBlock; active: boolean }) {
  return (
    <ol className="board-steps">
      {block.items.map((item, index) => (
        <li
          key={index}
          className={`board-step ${active ? "written" : ""}`}
          // Items stagger within the block so a multi-step line looks written
          // out rather than stamped down all at once.
          style={{ animationDelay: `${index * 260}ms` }}
        >
          <div className="board-step-body">
            <span className="board-step-math">
              <Math latex={item.math} />
              <BoardMark
                emphasis={item.emphasis}
                tone={item.emphasis_tone}
                visible={active}
              />
            </span>
            {item.operation && <p className="board-step-op">{item.operation}</p>}
            {item.note && <p className="board-step-note">{item.note}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Callout({ block }: { block: BoardCalloutBlock }) {
  return (
    <div className={`board-callout ${block.tone}`}>
      <span className="material-symbols-outlined" aria-hidden="true">
        {CALLOUT_ICON[block.tone]}
      </span>
      <p>{block.text}</p>
    </div>
  );
}

function ExpressionCompare({ block }: { block: BoardExpressionCompareBlock }) {
  return (
    <div className="board-compare">
      <div className="board-compare-row">
        <div className="board-compare-side">
          {block.left_label && <span className="board-compare-label">{block.left_label}</span>}
          <Math latex={block.left} className="board-math large" />
        </div>
        <span className="board-compare-relation" aria-hidden="true">
          {block.relation}
        </span>
        <div className="board-compare-side">
          {block.right_label && <span className="board-compare-label">{block.right_label}</span>}
          <Math latex={block.right} className="board-math large" />
        </div>
      </div>

      {block.rewrite_left && block.rewrite_right && (
        <div className="board-compare-row rewrite">
          <div className="board-compare-side">
            <Math latex={block.rewrite_left} />
          </div>
          <span className="board-compare-relation" aria-hidden="true">
            {block.relation}
          </span>
          <div className="board-compare-side">
            <Math latex={block.rewrite_right} />
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Renders one validated block.
 *
 * Returns null for a kind it does not know, so a frontend running against a
 * backend that gained a new block type degrades quietly instead of crashing.
 * Because BoardBlock is a discriminated union, TypeScript still flags any block
 * type added to types.ts that is not handled here.
 *
 * `active` means "this block has been written". It drives the entrance and the
 * hand-drawn marks, so a block that has not been reached yet is not in the
 * document at all rather than sitting there greyed out.
 */
export function BoardBlock({ block, active = true }: { block: Block; active?: boolean }) {
  const body = () => {
    switch (block.kind) {
      case "steps":
        return <Steps block={block} active={active} />;
      case "callout":
        return <Callout block={block} />;
      case "expression_compare":
        return <ExpressionCompare block={block} />;
      case "fraction_bars":
        return <BoardFractionBars block={block} />;
      case "number_line":
        return <BoardNumberLine block={block} />;
      case "coordinate_plane":
        return <BoardCoordinatePlane block={block} />;
      case "geometry_figure":
        return <BoardGeometryFigure block={block} />;
      default:
        return null;
    }
  };

  const content = body();
  if (!content) return null;

  return (
    <section
      className={`board-block board-block-${block.kind} ${active ? "written" : ""}`}
      aria-label={block.caption}
    >
      {content}
    </section>
  );
}
