import { act, fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { seriousViolations } from "@/test/axe";

import { useExplainLevel, useTextSelection } from "./selection";
import { SelectionToolbar } from "./SelectionToolbar";

const onQuote = vi.fn<(mode: "ask" | "explain", page: number, text: string, level: string) => void>();

function Harness() {
  const root = useRef<HTMLDivElement>(null);
  const toolbar = useRef<HTMLDivElement>(null);
  const { selected, close } = useTextSelection(root, toolbar);
  const [level, setLevel] = useExplainLevel();
  return (
    <div ref={root}>
      <div data-page="3">
        <span>Multi-head attention attends to information jointly.</span>
      </div>
      {selected && (
        <SelectionToolbar
          selection={selected}
          toolbarRef={toolbar}
          level={level}
          onLevel={setLevel}
          onExplain={() => { onQuote("explain", selected.page, selected.text, level); close(); }}
          onAsk={() => { onQuote("ask", selected.page, selected.text, level); close(); }}
        />
      )}
    </div>
  );
}

function selectText() {
  const node = screen.getByText(/Multi-head attention/).firstChild as Text;
  const range = document.createRange();
  range.setStart(node, 0);
  range.setEnd(node, 20);
  act(() => {
    const selection = document.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    document.dispatchEvent(new Event("selectionchange")); // keyboard selection path
  });
}

beforeEach(() => {
  onQuote.mockReset();
  localStorage.clear();
  document.getSelection()?.removeAllRanges();
});

describe("Spec 015 AC3: selection toolbar", () => {
  it("appears for selected text with Explain and Ask, and sends the page and text", async () => {
    const { container } = render(<Harness />);
    selectText();
    const toolbar = await screen.findByRole("toolbar", { name: "Selected text" });
    expect(await seriousViolations(container.ownerDocument.body)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Explain" }));
    expect(onQuote).toHaveBeenCalledWith("explain", 3, "Multi-head attention", "plain");
    expect(toolbar).not.toBeInTheDocument();
  });

  it("closes on Escape and on a click elsewhere", async () => {
    render(<Harness />);
    selectText();
    await screen.findByRole("toolbar", { name: "Selected text" });
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("toolbar", { name: "Selected text" })).toBeNull();
    selectText();
    await screen.findByRole("toolbar", { name: "Selected text" });
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("toolbar", { name: "Selected text" })).toBeNull();
  });

  it("AC4: remembers the Explain level on this device", async () => {
    const first = render(<Harness />);
    selectText();
    fireEvent.click(await screen.findByRole("radio", { name: "Expert" }));
    expect(screen.getByRole("radio", { name: "Expert" })).toHaveAttribute("aria-checked", "true");
    first.unmount();
    render(<Harness />);
    selectText();
    fireEvent.click(await screen.findByRole("button", { name: "Ask" }));
    expect(onQuote).toHaveBeenCalledWith("ask", 3, "Multi-head attention", "expert");
  });

  it("ignores selections outside the paper", () => {
    render(
      <>
        <p>Outside text</p>
        <Harness />
      </>,
    );
    const node = screen.getByText("Outside text").firstChild as Text;
    const range = document.createRange();
    range.selectNodeContents(node);
    act(() => {
      document.getSelection()?.addRange(range);
      document.dispatchEvent(new Event("selectionchange"));
    });
    expect(screen.queryByRole("toolbar", { name: "Selected text" })).toBeNull();
  });
});

describe("Spec 015: selection tip", () => {
  it("explains how to Explain or Ask once, then stays dismissed", async () => {
    const { SelectionTip } = await import("./SelectionTip");
    const first = render(<SelectionTip />);
    expect(screen.getByRole("note", { name: "Tip" })).toHaveTextContent(/Select text with the mouse to Explain it or Ask about it/);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss tip" }));
    expect(screen.queryByRole("note", { name: "Tip" })).toBeNull();
    first.unmount();
    render(<SelectionTip />);
    expect(screen.queryByRole("note", { name: "Tip" })).toBeNull();
  });
});
