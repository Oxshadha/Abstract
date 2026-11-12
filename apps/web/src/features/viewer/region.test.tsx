import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PageBox } from "./citation-context";
import { RegionLayer } from "./RegionLayer";

const BOX: PageBox = { x: 0.2, y: 0.3, width: 0.4, height: 0.2 };

/** Page fractions compared to 6 decimals (floating point). */
const near = (box: PageBox) => ({
  x: expect.closeTo(box.x, 6) as number,
  y: expect.closeTo(box.y, 6) as number,
  width: expect.closeTo(box.width, 6) as number,
  height: expect.closeTo(box.height, 6) as number,
});

function renderLayer(box: PageBox | null) {
  const onChange = vi.fn();
  const onAsk = vi.fn();
  const onCancel = vi.fn();
  render(<RegionLayer page={4} box={box} onChange={onChange} onAsk={onAsk} onCancel={onCancel} />);
  return { onChange, onAsk, onCancel };
}

describe("Ask about this region (spec 009 AC10)", () => {
  it("draws a box by dragging, in page fractions", () => {
    const { onChange } = renderLayer(null);
    const layer = screen.getByLabelText("Draw a region on page 4");
    layer.getBoundingClientRect = () => ({ left: 0, top: 0, width: 500, height: 1000, right: 500, bottom: 1000, x: 0, y: 0, toJSON: () => ({}) });
    layer.setPointerCapture = () => undefined;
    fireEvent.pointerDown(layer, { clientX: 100, clientY: 200, pointerId: 1 });
    fireEvent.pointerMove(layer, { clientX: 300, clientY: 400, pointerId: 1 });
    expect(onChange).toHaveBeenLastCalledWith(near({ x: 0.2, y: 0.2, width: 0.4, height: 0.2 }));
  });

  it("moves with the arrow keys and resizes with Shift, kept inside the page", () => {
    const { onChange } = renderLayer(BOX);
    const region = screen.getByRole("group", { name: /Selected region on page 4/ });
    fireEvent.keyDown(region, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith(near({ ...BOX, x: 0.21 }));
    fireEvent.keyDown(region, { key: "ArrowDown", shiftKey: true });
    expect(onChange).toHaveBeenLastCalledWith(near({ ...BOX, height: 0.21 }));
  });

  it("asks with the button or Enter, and cancels with Escape", () => {
    const { onAsk, onCancel } = renderLayer(BOX);
    fireEvent.click(screen.getByRole("button", { name: "Ask about this region" }));
    expect(onAsk).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(screen.getByRole("group", { name: /Selected region/ }), { key: "Enter" });
    expect(onAsk).toHaveBeenCalledTimes(2);
    fireEvent.keyDown(screen.getByRole("group", { name: /Selected region/ }), { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("offers no Ask for a box under the 2% minimum", () => {
    renderLayer({ x: 0.2, y: 0.3, width: 0.01, height: 0.2 });
    expect(screen.queryByRole("button", { name: "Ask about this region" })).toBeNull();
  });
});
