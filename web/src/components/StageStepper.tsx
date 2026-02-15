import { Steps } from 'antd';
import { STAGE_ORDER, STAGE_LABELS } from '../types';

interface Props {
  status: string;
}

export default function StageStepper({ status }: Props) {
  const currentIndex = STAGE_ORDER.indexOf(status as typeof STAGE_ORDER[number]);

  return (
    <Steps
      current={currentIndex >= 0 ? currentIndex : 0}
      size="small"
      items={STAGE_ORDER.map((s) => ({
        title: STAGE_LABELS[s],
      }))}
    />
  );
}
