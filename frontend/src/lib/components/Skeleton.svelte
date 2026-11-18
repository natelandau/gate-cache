<!--
  @component
  A shimmering placeholder block shown while data loads. It stays invisible for its first
  200ms, so a fast load never flashes a skeleton.

  Props:
  - `height`: block height in pixels
  - `width`: CSS width (default "100%")
-->
<script lang="ts">
  interface Props {
    height: number;
    width?: string;
  }

  let { height, width = "100%" }: Props = $props();
</script>

<span class="skeleton" aria-hidden="true" style:height="{height}px" style:width></span>

<style>
  .skeleton {
    display: block;
    border-radius: var(--radius-chip);
    background: linear-gradient(
      90deg,
      var(--surface-sunken) 0%,
      var(--surface-hover) 50%,
      var(--surface-sunken) 100%
    );
    background-size: 200% 100%;
    opacity: 0;
    animation:
      appear var(--dur-fast) var(--ease-in) 200ms forwards,
      shimmer 1.4s linear infinite;
  }

  @keyframes appear {
    to {
      opacity: 1;
    }
  }
</style>
