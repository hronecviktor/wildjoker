<script lang="ts">
  // First screen: pick the game (Wild Joker or Gin) and a name, then create
  // a game or join one by code. Opened from an invite link (/j/ABCD) it only
  // asks for the name: the room already has its game.
  import { errorText, t } from "../i18n/index.svelte";
  import { ServerError } from "../lib/connection.svelte";
  import { conn, startTutorial } from "../lib/session.svelte";
  import { load, save } from "../lib/storage";
  import { canInstall, promptInstall } from "../lib/install.svelte";
  import type { GameKind } from "../lib/protocol";
  import GinRules from "./GinRules.svelte";
  import InstallHelp from "./InstallHelp.svelte";
  import LangPicker from "./LangPicker.svelte";

  let { invite = null }: { invite?: string | null } = $props();

  let name = $state(load("name", ""));
  let code = $state("");
  let busy = $state(false);
  let error = $state("");
  let installHelp = $state(false);
  let rules = $state(false);
  let kind = $state<GameKind>(load<GameKind>("game", "wild") === "gin" ? "gin" : "wild");

  function pick(k: GameKind) {
    kind = k;
    save("game", k);
  }

  async function installApp() {
    if (!(await promptInstall())) installHelp = true;
  }

  const nameOk = $derived(name.trim().length >= 1 && name.trim().length <= 20);
  const codeOk = $derived(/^[A-Za-z]{4}$/.test(code.trim()));

  async function go(action: () => Promise<void>) {
    if (!nameOk || busy) return;
    busy = true;
    error = "";
    save("name", name.trim());
    try {
      await action();
      history.replaceState(null, "", `/j/${conn.code}`);
    } catch (e) {
      if (!(e instanceof ServerError)) throw e;
      error = errorText(e.code);
    } finally {
      busy = false;
    }
  }

  const create = () => go(() => conn.create(name.trim(), kind));
  const join = (c: string) => go(() => conn.joinRoom(c.trim().toUpperCase(), name.trim()));

  async function tutorial() {
    if (kind === "gin") {
      rules = true;
      return;
    }
    if (busy) return;
    busy = true;
    error = "";
    if (nameOk) save("name", name.trim());
    try {
      await startTutorial(name);
    } catch (e) {
      if (!(e instanceof ServerError)) throw e;
      error = errorText(e.code);
    } finally {
      busy = false;
    }
  }
</script>

<main class="start">
  <div class="top"><LangPicker /></div>
  {#if invite}
    <h1 class="logo"><span aria-hidden="true">🃏</span> Wild Joker</h1>
  {:else}
    <h1 class="logo">
      <span aria-hidden="true">{kind === "gin" ? "♣" : "🃏"}</span>
      {kind === "gin" ? t("start.game_gin") : "Wild Joker"}
    </h1>
    <p class="tagline">{kind === "gin" ? t("start.tagline_gin") : t("start.tagline")}</p>
    <div class="games" role="radiogroup" aria-label={t("start.game")}>
      {#each [["wild", "🃏", t("start.game_wild")], ["gin", "♣", t("start.game_gin")]] as [k, icon, label] (k)}
        <button
          type="button"
          role="radio"
          aria-checked={kind === k}
          class:active={kind === k}
          data-testid="game-{k}"
          onclick={() => pick(k as GameKind)}><span aria-hidden="true">{icon}</span> {label}</button
        >
      {/each}
    </div>
  {/if}

  <form
    class="panel"
    onsubmit={(e) => {
      e.preventDefault();
      if (invite) join(invite);
      else create();
    }}
  >
    {#if invite}
      <p class="invite">{t("start.invited", { code: invite })}</p>
    {/if}
    <label class="field">
      <span>{t("start.name")}</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input
        bind:value={name}
        maxlength="20"
        autocomplete="nickname"
        autofocus
        placeholder={t("start.name_placeholder")}
        data-testid="name"
      />
    </label>
    {#if invite}
      <button class="btn primary big" disabled={!nameOk || busy} data-testid="join">
        {t("start.join_game")}
      </button>
      <a class="link" href="/">{t("start.other_game")}</a>
    {:else}
      <button class="btn primary big" disabled={!nameOk || busy} data-testid="create">
        {t("start.create")}
      </button>
    {/if}
  </form>

  {#if !invite}
    <form
      class="panel join-row"
      onsubmit={(e) => {
        e.preventDefault();
        if (codeOk) join(code);
      }}
    >
      <label class="field">
        <span>{t("start.code")}</span>
        <input
          bind:value={code}
          maxlength="4"
          autocapitalize="characters"
          autocomplete="off"
          spellcheck="false"
          class="code-input"
          placeholder="ABCD"
          data-testid="code"
        />
      </label>
      <button class="btn big" disabled={!nameOk || !codeOk || busy} data-testid="join-code">
        {t("start.join")}
      </button>
    </form>
  {/if}

  {#if !invite}
    <button type="button" class="btn big tutorial" disabled={busy} onclick={tutorial} data-testid="tutorial-start">
      🎓 {t("start.tutorial")}
    </button>
  {/if}
  {#if canInstall()}
    <button type="button" class="btn big install" onclick={installApp} data-testid="install">
      📲 {t("install.button")}
    </button>
  {/if}
  {#if error}<p class="error" role="alert">{error}</p>{/if}
</main>

{#if installHelp}<InstallHelp onclose={() => (installHelp = false)} />{/if}
{#if rules}<GinRules onclose={() => (rules = false)} />{/if}

<style>
  .start {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 14px;
    width: 100%;
    max-width: 420px;
    margin: 0 auto;
    padding: 12px 16px 32px;
  }
  .top {
    display: flex;
    justify-content: flex-end;
  }
  .logo {
    margin: 12px 0 0;
    font-size: 40px;
    text-align: center;
    letter-spacing: -0.02em;
  }
  .tagline {
    margin: 0 0 8px;
    color: var(--muted);
    text-align: center;
  }
  .games {
    display: flex;
    gap: 4px;
    padding: 4px;
    border-radius: 14px;
    background: var(--panel);
  }
  .games button {
    flex: 1;
    min-height: 44px;
    border: 0;
    border-radius: 10px;
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-weight: 700;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  .games button.active {
    background: var(--accent);
    color: #fff;
  }
  .games button:focus-visible {
    outline: 3px solid #39a0ff;
    outline-offset: 2px;
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    border-radius: 14px;
    background: var(--panel);
  }
  .join-row {
    flex-direction: row;
    align-items: flex-end;
  }
  .join-row .field {
    flex: 1;
  }
  .join-row .btn {
    white-space: nowrap;
  }
  .invite {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }
  .code-input {
    text-transform: uppercase;
    letter-spacing: 0.3em;
    font-weight: 700;
  }
  .link {
    color: var(--muted);
    text-align: center;
  }
  .error {
    margin: 0;
    padding: 10px 12px;
    border-radius: 10px;
    background: #5c1d22;
    color: #ffd6d9;
  }
</style>
