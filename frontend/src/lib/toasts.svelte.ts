// Short messages at the top of the screen (errors, events).

export interface Toast {
  id: number;
  text: string;
  kind: "info" | "error";
}

let nextId = 1;
export const toasts = $state<Toast[]>([]);

export function toast(text: string, kind: Toast["kind"] = "info", ms = 3500): void {
  const id = nextId++;
  toasts.push({ id, text, kind });
  if (toasts.length > 3) toasts.shift();
  setTimeout(() => dismiss(id), ms);
}

export function dismiss(id: number): void {
  const i = toasts.findIndex((t) => t.id === id);
  if (i >= 0) toasts.splice(i, 1);
}
