<template>
  <div class="dcs-process-diagram" :aria-label="title">
    <div
      v-for="line in lines"
      :key="line.id"
      class="process-line"
      :class="[line.tone || 'white', { dashed: line.dashed, arrow: line.arrow !== false }]"
      :style="lineStyle(line)"
    ></div>

    <div
      v-for="label in labels"
      :key="label.id"
      class="process-label"
      :style="boxStyle(label)"
    >
      {{ label.text }}
    </div>

    <div
      v-for="vessel in vessels"
      :key="vessel.id"
      class="process-vessel"
      :class="vessel.type || 'tower'"
      :style="boxStyle(vessel)"
    >
      <div class="vessel-head"></div>
      <div v-for="section in vessel.sections || []" :key="section.id" class="vessel-section" :class="section.className">
        {{ section.label }}
      </div>
      <div v-if="vessel.pack" class="vessel-pack"></div>
      <div v-if="vessel.liquid" class="vessel-liquid" :style="{ height: vessel.liquid }"></div>
    </div>

    <div
      v-for="valve in valves"
      :key="valve.id"
      class="process-valve"
      :class="[valve.tone || 'green', valve.shape || 'bowtie']"
      :style="boxStyle(valve)"
      :title="valve.label"
    ></div>

    <div
      v-for="instrument in instruments"
      :key="instrument.id"
      class="process-instrument"
      :class="instrument.tone || 'normal'"
      :style="boxStyle(instrument)"
    >
      <span>{{ instrument.tag }}</span>
      <strong>{{ instrument.value }}</strong>
      <em>{{ instrument.unit }}</em>
    </div>

    <div
      v-for="junction in junctions"
      :key="junction.id"
      class="process-junction"
      :class="junction.tone || 'white'"
      :style="boxStyle(junction)"
    ></div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: 'DCS process diagram' },
  lines: { type: Array, default: () => [] },
  labels: { type: Array, default: () => [] },
  valves: { type: Array, default: () => [] },
  vessels: { type: Array, default: () => [] },
  instruments: { type: Array, default: () => [] },
  junctions: { type: Array, default: () => [] },
})

function pct(value) {
  return typeof value === 'number' ? `${value}%` : value
}

function boxStyle(item = {}) {
  return {
    left: pct(item.x),
    top: pct(item.y),
    width: pct(item.width),
    height: pct(item.height),
    transform: item.centered === false ? undefined : 'translate(-50%, -50%)',
  }
}

function lineStyle(line = {}) {
  return {
    left: pct(line.x),
    top: pct(line.y),
    width: pct(line.length),
    transform: `rotate(${line.rotate || 0}deg)`,
  }
}
</script>

<style scoped>
.dcs-process-diagram {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background:
    radial-gradient(circle at 58% 44%, rgba(31, 96, 138, .26), transparent 34%),
    linear-gradient(180deg, #082d43, #06283b);
  box-shadow: inset 0 0 0 3px #000, inset 0 0 90px rgba(0, 0, 0, .28);
}

.process-line {
  position: absolute;
  height: 3px;
  transform-origin: left center;
}

.process-line.white {
  background: #d9edf8;
  color: #d9edf8;
  box-shadow: 0 0 2px rgba(255, 255, 255, .35);
}

.process-line.magenta {
  background: #e000d7;
  color: #e000d7;
}

.process-line.signal {
  height: 2px;
  background: transparent;
  border-top: 2px dashed rgba(217, 237, 248, .58);
  color: rgba(217, 237, 248, .58);
}

.process-line.arrow::after {
  content: '';
  position: absolute;
  right: -1px;
  top: -4px;
  width: 0;
  height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 18px solid currentColor;
}

.process-label {
  position: absolute;
  color: #d9edf8;
  font-size: clamp(11px, .82vw, 14px);
  font-weight: 800;
  text-shadow: 0 1px 0 #000;
  white-space: nowrap;
}

.process-vessel {
  position: absolute;
  border: 2px solid #758084;
  background: #b9bec0;
  color: #101820;
  overflow: hidden;
  box-shadow: 0 0 0 1px #000;
}

.process-vessel.tower {
  border-radius: 999px;
}

.vessel-head,
.vessel-section,
.vessel-pack,
.vessel-liquid {
  position: absolute;
  left: 0;
  right: 0;
}

.vessel-head {
  top: 0;
  height: 18%;
  border-bottom: 2px solid #697174;
}

.vessel-section {
  display: grid;
  place-items: center;
  font-size: clamp(13px, 1vw, 20px);
  font-weight: 900;
}

.vessel-section.upper {
  top: 18%;
  height: 24%;
}

.vessel-section.lower {
  top: 62%;
  height: 25%;
  border-top: 2px solid #697174;
}

.vessel-pack {
  top: 42%;
  height: 20%;
  border-top: 2px solid #697174;
  border-bottom: 2px solid #697174;
  background:
    linear-gradient(135deg, transparent 47%, #697174 48%, #697174 52%, transparent 53%),
    linear-gradient(45deg, transparent 47%, #697174 48%, #697174 52%, transparent 53%);
}

.vessel-liquid {
  left: 27%;
  right: 27%;
  bottom: 8%;
  background: #d300c8;
  border: 1px solid #555;
}

.process-valve {
  position: absolute;
  width: 20px;
  height: 20px;
  border-radius: 50%;
}

.process-valve::before,
.process-valve::after {
  content: '';
  position: absolute;
  top: 4px;
  width: 0;
  height: 0;
  border-top: 6px solid transparent;
  border-bottom: 6px solid transparent;
}

.process-valve::before {
  left: 1px;
  border-right: 9px solid currentColor;
}

.process-valve::after {
  right: 1px;
  border-left: 9px solid currentColor;
}

.process-valve.green {
  color: #00ff28;
  background: #00ff28;
}

.process-valve.red {
  color: #ff1717;
  background: #ff1717;
}

.process-valve.gray {
  color: #c0c4c7;
  background: #c0c4c7;
}

.process-instrument {
  position: absolute;
  display: grid;
  grid-template-columns: minmax(46px, auto) auto;
  min-width: 78px;
  color: #d9edf8;
  font-family: Arial, "Segoe UI", sans-serif;
  font-size: clamp(10px, .72vw, 13px);
}

.process-instrument span {
  grid-column: 1 / 3;
  color: #8baabe;
  font-weight: 800;
}

.process-instrument strong {
  min-width: 46px;
  padding: 2px 7px;
  background: #1d5d89;
  color: #d9edf8;
  text-align: center;
}

.process-instrument em {
  padding-left: 6px;
  color: #d9edf8;
  font-style: normal;
  white-space: nowrap;
}

.process-instrument.invalid strong {
  background: #18435e;
}

.process-junction {
  position: absolute;
  width: 14px;
  height: 14px;
  border-radius: 50%;
}

.process-junction.green {
  background: #00ff28;
}

.process-junction.red {
  background: #ff1717;
}

.process-junction.white {
  background: #c8d6de;
}
</style>
