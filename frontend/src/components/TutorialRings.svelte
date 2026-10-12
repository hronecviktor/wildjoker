<script lang="ts">
  // Pulsing rings around what a tutorial step wants tapped next.
  let { targets }: { targets: string[] } = $props();

  // Rings around the targets, following them as the layout changes.
  let rings = $state<{ x: number; y: number; w: number; h: number }[]>([]);
  $effect(() => {
    const selectors = targets;
    let frame = 0;
    let last = "";
    const measure = () => {
      const found = selectors.flatMap((sel) => [...document.querySelectorAll(sel)]);
      const next = found.map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left, y: r.top, w: r.width, h: r.height };
      });
      const json = JSON.stringify(next);
      if (json !== last) [last, rings] = [json, next];
      frame = requestAnimationFrame(measure);
    };
    measure();
    return () => cancelAnimationFrame(frame);
  });

</script>

{#each rings as r, i (i)}
  <div
    class="ring"
    aria-hidden="true"
    style:left="{r.x - 4}px"
    style:top="{r.y - 4}px"
    style:width="{r.w + 8}px"
    style:height="{r.h + 8}px"
  ></div>
{/each}

<style>
  .ring {
    position: fixed;
    z-index: 60;
    border: 3px solid #f5b301;
    border-radius: 12px;
    pointer-events: none;
    animation: ring 1.2s ease-in-out infinite;
  }
  @keyframes ring {
    0%,
    100% {
      box-shadow: 0 0 0 0 rgb(245 179 1 / 0.7);
    }
    50% {
      box-shadow: 0 0 0 8px rgb(245 179 1 / 0);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .ring {
      animation: none;
    }
  }
</style>
