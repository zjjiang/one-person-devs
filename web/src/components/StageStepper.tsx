import { Steps } from "antd";
import { STAGE_LABELS, getStageOrder } from "../types";

interface Props {
  status: string;
  mode?: "full" | "light";
}

export default function StageStepper({ status, mode = "full" }: Props) {
  const stages = getStageOrder(mode);
  const currentIndex = (stages as readonly string[]).indexOf(status);

  return (
    <Steps
      current={currentIndex >= 0 ? currentIndex : 0}
      size="small"
      items={stages.map((s) => ({
        title: STAGE_LABELS[s],
      }))}
    />
  );
}
