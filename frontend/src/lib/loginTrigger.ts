// The header login button receives __reactProps while the host root is still
// dehydrated. React then stopPropagations the click and never runs onClick.
// A capture listener registered when this module loads runs before that, and
// the opener is applied again once AuthProvider has committed.

export const LOGIN_TRIGGER_SELECTOR = "[data-login-trigger]";

type ClickTarget = {
  nodeType?: number;
  parentElement?: ClickTarget | null;
  closest?: (selector: string) => unknown;
};

export type LoginListenTarget = {
  addEventListener: (
    type: string,
    listener: (event: { target: EventTarget | null }) => void,
    capture?: boolean,
  ) => void;
  removeEventListener: (
    type: string,
    listener: (event: { target: EventTarget | null }) => void,
    capture?: boolean,
  ) => void;
};

export type LoginTrigger = {
  bind: (open: () => void) => () => void;
  hasIntent: () => boolean;
  clearIntent: () => void;
  dispose: () => void;
};

export function isLoginTriggerTarget(target: EventTarget | null): boolean {
  let node: ClickTarget | null = target && typeof target === "object" ? (target as ClickTarget) : null;
  if (node?.nodeType === 3) node = node.parentElement ?? null;
  if (!node || typeof node.closest !== "function") return false;
  return node.closest(LOGIN_TRIGGER_SELECTOR) != null;
}

export function createLoginTrigger(target: LoginListenTarget): LoginTrigger {
  let pending = false;
  let opener: (() => void) | null = null;

  const onClick = (event: { target: EventTarget | null }) => {
    if (!isLoginTriggerTarget(event.target)) return;
    pending = true;
    opener?.();
  };

  target.addEventListener("click", onClick, true);

  return {
    bind(open) {
      opener = open;
      if (pending) open();
      return () => {
        if (opener === open) opener = null;
      };
    },
    hasIntent: () => pending,
    clearIntent() {
      pending = false;
    },
    dispose() {
      target.removeEventListener("click", onClick, true);
      opener = null;
    },
  };
}

let installed: LoginTrigger | null = null;

export function installLoginTrigger(): void {
  if (installed || typeof window === "undefined") return;
  installed = createLoginTrigger(window);
}

export function bindLoginOpener(open: () => void): () => void {
  installLoginTrigger();
  if (!installed) return () => {};
  return installed.bind(open);
}

export function clearLoginIntent(): void {
  installed?.clearIntent();
}
