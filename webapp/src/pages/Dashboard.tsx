import { motion } from 'framer-motion';
import type { State } from '../lib/types';
import { CountdownCard } from '../components/CountdownCard';
import { TodayWorkout } from '../components/TodayWorkout';
import { WeeklySchedule } from '../components/WeeklySchedule';
import { VolumeChart } from '../components/VolumeChart';
import { KpiTiles } from '../components/KpiTiles';

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
};
const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' as const } },
};

export function Dashboard({ state, onChanged }: { state: State; onChanged: () => void }) {
  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4"
    >
      <motion.div variants={item} className="md:col-span-2"><CountdownCard state={state} /></motion.div>
      <motion.div variants={item} className="md:col-span-2"><TodayWorkout state={state} onChanged={onChanged} /></motion.div>
      <motion.div variants={item} className="md:col-span-2"><WeeklySchedule state={state} /></motion.div>
      <motion.div variants={item} className="md:col-span-2"><KpiTiles state={state} /></motion.div>
      <motion.div variants={item} className="md:col-span-2 xl:col-span-4"><VolumeChart state={state} /></motion.div>
    </motion.div>
  );
}
