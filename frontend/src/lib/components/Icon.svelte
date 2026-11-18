<!--
  @component
  One Lucide icon by name. Only the icons listed here ship in the bundle, so add a name to
  `ICONS` before using it.

  Props:
  - `name`: the Lucide icon name, such as "info"
  - `size`: width and height in pixels (default 16)
  - `label`: accessible name for an icon that carries meaning on its own; without it the icon
    is decorative and hidden from screen readers
-->
<script lang="ts" module>
  import Activity from "@lucide/svelte/icons/activity";
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowRight from "@lucide/svelte/icons/arrow-right";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import ArrowUpRight from "@lucide/svelte/icons/arrow-up-right";
  import Calendar from "@lucide/svelte/icons/calendar";
  import CalendarDays from "@lucide/svelte/icons/calendar-days";
  import CheckCheck from "@lucide/svelte/icons/check-check";
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import CircleAlert from "@lucide/svelte/icons/circle-alert";
  import FolderGit2 from "@lucide/svelte/icons/folder-git-2";
  import Hourglass from "@lucide/svelte/icons/hourglass";
  import Inbox from "@lucide/svelte/icons/inbox";
  import Info from "@lucide/svelte/icons/info";
  import LayoutDashboard from "@lucide/svelte/icons/layout-dashboard";
  import ListChecks from "@lucide/svelte/icons/list-checks";
  import Moon from "@lucide/svelte/icons/moon";
  import Sun from "@lucide/svelte/icons/sun";
  import SunMoon from "@lucide/svelte/icons/sun-moon";
  import TrendingDown from "@lucide/svelte/icons/trending-down";
  import TrendingUp from "@lucide/svelte/icons/trending-up";
  import TriangleAlert from "@lucide/svelte/icons/triangle-alert";
  import X from "@lucide/svelte/icons/x";

  const ICONS = {
    activity: Activity,
    "arrow-down": ArrowDown,
    "arrow-right": ArrowRight,
    "arrow-up": ArrowUp,
    "arrow-up-right": ArrowUpRight,
    calendar: Calendar,
    "calendar-days": CalendarDays,
    "check-check": CheckCheck,
    "chevron-down": ChevronDown,
    "circle-alert": CircleAlert,
    "folder-git-2": FolderGit2,
    hourglass: Hourglass,
    inbox: Inbox,
    info: Info,
    "layout-dashboard": LayoutDashboard,
    "list-checks": ListChecks,
    moon: Moon,
    sun: Sun,
    "sun-moon": SunMoon,
    "trending-down": TrendingDown,
    "trending-up": TrendingUp,
    "triangle-alert": TriangleAlert,
    x: X,
  };

  export type IconName = keyof typeof ICONS;
</script>

<script lang="ts">
  interface Props {
    name: IconName;
    size?: number;
    label?: string;
  }

  let { name, size = 16, label }: Props = $props();

  const Glyph = $derived(ICONS[name]);
</script>

{#if label}
  <Glyph {size} strokeWidth={1.75} role="img" aria-label={label} />
{:else}
  <Glyph {size} strokeWidth={1.75} aria-hidden="true" />
{/if}
