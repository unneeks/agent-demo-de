function selectMessageText(node) {
  const copyable = node.querySelector("[data-pre-plain-text] + div span.selectable-text");
  const nested = node.querySelector("span.selectable-text");
  return copyable?.textContent?.trim() || nested?.textContent?.trim() || "";
}

function getAuthor(node) {
  if (node.classList.contains("message-out")) {
    return "self";
  }
  if (node.classList.contains("message-in")) {
    return "other";
  }
  return "system";
}

export function getConversationId() {
  const header = document.querySelector("header [title]");
  return header?.getAttribute("title") || "whatsapp-conversation";
}

export function getConversationTitle() {
  const header = document.querySelector("header [title]");
  return header?.getAttribute("title") || "Current chat";
}

export function parseMessageNodes(root = document) {
  const nodes = [...root.querySelectorAll("div.message-in, div.message-out")];

  return nodes
    .map((node, index) => {
      const text = selectMessageText(node);
      if (!text) {
        return null;
      }

      const id =
        node.dataset.id ||
        node.getAttribute("data-id") ||
        `${getConversationId()}-${index}-${text.slice(0, 16)}`;

      return {
        id,
        conversationId: getConversationId(),
        author: getAuthor(node),
        text,
        timestamp:
          node.querySelector("[data-pre-plain-text]")?.getAttribute("data-pre-plain-text") ||
          null,
        node
      };
    })
    .filter(Boolean);
}
