<script lang="ts">
  import { i18n, LANG_NAMES, LANGS, t, type Lang } from "../i18n/index.svelte";
</script>

<select
  class="lang"
  aria-label={t("app.language")}
  value={i18n.lang}
  onchange={(e) => (i18n.lang = e.currentTarget.value as Lang)}
>
  {#each Object.keys(LANGS) as lang (lang)}
    <option value={lang}>{LANG_NAMES[lang as Lang]}</option>
  {/each}
</select>

<style>
  .lang {
    min-height: 40px;
    padding: 0 6px;
    border: 1px solid rgb(255 255 255 / 0.25);
    border-radius: 8px;
    background: transparent;
    color: inherit;
    font: inherit;
    font-size: 14px;
  }
  .lang option {
    color: #111;
  }
</style>
