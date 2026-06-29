import { Shell } from "@/components/shell";
import { MetricCards } from "@/components/metric-cards";
import { ScreenerTable } from "@/components/screener-table";

export default function Home() {
  return (
    <Shell active="Radar">
      <MetricCards />
      <ScreenerTable />
    </Shell>
  );
}
