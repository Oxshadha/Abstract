import { Mark, mergeAttributes, type Extensions } from "@tiptap/core";
import Blockquote from "@tiptap/extension-blockquote";
import Bold from "@tiptap/extension-bold";
import Document from "@tiptap/extension-document";
import HardBreak from "@tiptap/extension-hard-break";
import Heading from "@tiptap/extension-heading";
import Italic from "@tiptap/extension-italic";
import { BulletList, ListItem, OrderedList } from "@tiptap/extension-list";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { Placeholder, UndoRedo } from "@tiptap/extensions";

/**
 * A page source in a note (spec 014 AC2): "[1]" from a saved answer, carrying the page and the
 * quoted sentence. Clicking it opens the paper there, highlighted, like a chat citation.
 */
export const Source = Mark.create({
  name: "source",
  inclusive: false,
  excludes: "_",
  addAttributes() {
    return {
      page: {
        default: 1,
        parseHTML: (el: HTMLElement) => Number(el.getAttribute("data-page")) || 1,
        renderHTML: (attrs: { page: number }) => ({ "data-page": String(attrs.page) }),
      },
      quote: {
        default: "",
        parseHTML: (el: HTMLElement) => el.getAttribute("data-quote") ?? "",
        renderHTML: (attrs: { quote: string }) => ({ "data-quote": attrs.quote }),
      },
    };
  },
  parseHTML() {
    return [{ tag: "span[data-source]" }];
  },
  renderHTML({ HTMLAttributes }) {
    const page = String(HTMLAttributes["data-page"] ?? "");
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-source": "",
        title: `Open page ${page}`,
        class: "cursor-pointer rounded-sm px-0.5 font-ui text-sm font-medium underline decoration-border-strong underline-offset-2 hover:bg-muted",
      }),
      0,
    ];
  },
});

/**
 * Only what the formatting bar offers (D95): the API refuses anything else, and pasted content is
 * reduced to these nodes and marks by the schema (no links, images or raw HTML).
 */
export function notesExtensions(placeholder: string): Extensions {
  return [
    Document,
    Paragraph,
    Text,
    HardBreak,
    Bold,
    Italic,
    Heading.configure({ levels: [1, 2, 3] }),
    BulletList,
    OrderedList,
    ListItem,
    Blockquote,
    Source,
    UndoRedo,
    Placeholder.configure({ placeholder }),
  ];
}
