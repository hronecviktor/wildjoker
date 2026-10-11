<script lang="ts">
  // First screen: pick a name, then create a game or join one by code.
  // Opened from an invite link (/j/ABCD) it only asks for the name.
  import { errorText, t } from "../i18n/index.svelte";
  import { ServerError } from "../lib/connection.svelte";
  import { conn } from "../lib/session.svelte";
  import { load, save } from "../lib/storage";
  import LangPicker from "./LangPicker.svelte";

  let { invite = null }: { invite?: string | null } = $props();

  let name = $state(load("name", ""));
  let code = $state("");
  let busy = $state(false);
  let error = $state("");

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

  const create = () => go(() => conn.create(name.trim()));
  const join = (c: string) => go(() => conn.joinRoom(c.trim().toUpperCase(), name.trim()));
</script>

<main class="start">
  <div class="top"><LangPicker /></div>
  <h1 class="logo"><span aria-hidden="true">🃏</span> Wild Joker</h1>
  <p class="tagline">{t("start.tagline")}</p>

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

  {#if error}<p class="error" role="alert">{error}</p>{/if}
</main>

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
