import { useTranslation } from "react-i18next";
import { assetUrl } from "../runtimeConfig";

export function RaceRewards({ rewards }: { rewards: readonly [number, number] }) {
  const { t } = useTranslation();
  return <div className="reward">
    <span><img src={assetUrl(`assets/score-chips/gold-trophy-${rewards[0]}.webp`)} alt={`${t("race:rewards.first")} ${rewards[0]}`} /></span>
    <span><img src={assetUrl(`assets/score-chips/silver-rosette-${rewards[1]}.webp`)} alt={`${t("race:rewards.second")} ${rewards[1]}`} /></span>
  </div>;
}
