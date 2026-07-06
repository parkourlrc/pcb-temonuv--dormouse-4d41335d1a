// Zigbee2MQTT external converter for the Dormouse temperature + humidity sensor.
//
// Install: copy to your Z2M data dir and reference it in configuration.yaml:
//   external_converters:
//     - dormouse.js
// Then restart Z2M and re-interview the device.
//
// ZHA note: standard temperature + battery work with no config. The custom
// debug cluster below, however, needs a ZHA quirk (zha-device-handlers) to
// surface in ZHA — only Zigbee2MQTT gets it "for free" via this converter.

const fz = require('zigbee-herdsman-converters/converters/fromZigbee');
const exposes = require('zigbee-herdsman-converters/lib/exposes');
const reporting = require('zigbee-herdsman-converters/lib/reporting');
const e = exposes.presets;
const ea = exposes.access;

const DEBUG_CLUSTER = 0xfc10;
const MFG = 0x1002; // must match MGM_MANUFACTURER_CODE in src/app.h + the ZAP

// --- custom debug cluster converters ---------------------------------------
// NOTE: newer Z2M prefers registering custom clusters via
// device.addCustomCluster(...). Reading by numeric attribute id (below) works
// on the classic converter API; adapt if your Z2M version requires the cluster
// to be declared first.
const fzLocal = {
    debug: {
        cluster: DEBUG_CLUSTER,
        type: ['attributeReport', 'readResponse'],
        convert: (model, msg, publish, options, meta) => {
            const d = msg.data;
            const out = {};
            if (d['0'] !== undefined) out.debug_mode = d['0'] ? 'ON' : 'OFF';
            if (d['1'] !== undefined) out.debug_log = String(d['1']);
            if (d['2'] !== undefined) out.debug_status = d['2'];
            if (d['3'] !== undefined) out.sample_interval = d['3'];
            return out;
        },
    },
};

const tzLocal = {
    debug_mode: {
        key: ['debug_mode'],
        convertSet: async (entity, key, value, meta) => {
            const on = value === 'ON' || value === true || value === 1;
            await entity.write(DEBUG_CLUSTER, {0x0000: {value: on ? 1 : 0, type: 0x10}},
                {manufacturerCode: MFG});
            return {state: {debug_mode: on ? 'ON' : 'OFF'}};
        },
        convertGet: async (entity, key, meta) => {
            await entity.read(DEBUG_CLUSTER, [0x0000], {manufacturerCode: MFG});
        },
    },
    sample_interval: {
        key: ['sample_interval'],
        convertSet: async (entity, key, value, meta) => {
            await entity.write(DEBUG_CLUSTER, {0x0003: {value, type: 0x21}},
                {manufacturerCode: MFG});
            return {state: {sample_interval: value}};
        },
        convertGet: async (entity, key, meta) => {
            await entity.read(DEBUG_CLUSTER, [0x0003], {manufacturerCode: MFG});
        },
    },
};

module.exports = {
    zigbeeModel: ['Dormouse'],           // Basic cluster modelId (must match the ZAP)
    model: 'Dormouse',
    vendor: 'DIY',
    description: 'Dormouse — CR2032 Zigbee temperature + humidity sensor (MGM210L, sleepy end device)',
    fromZigbee: [fz.temperature, fz.humidity, fz.battery, fzLocal.debug],
    toZigbee: [tzLocal.debug_mode, tzLocal.sample_interval],
    exposes: [
        e.temperature(), e.humidity(), e.battery(), e.battery_voltage(),
        exposes.binary('debug_mode', ea.ALL, 'ON', 'OFF')
            .withDescription('10 s sampling + live debug log. Drains the coin cell — bench use only.'),
        exposes.text('debug_log', ea.STATE)
            .withDescription('Last firmware debug line (best-effort; RTT is the full log).'),
        exposes.numeric('debug_status', ea.STATE)
            .withDescription('Last read status: 0=OK, 1=I2C error, 2=CRC error.'),
        exposes.numeric('sample_interval', ea.ALL).withUnit('s')
            .withValueMin(1).withValueMax(3600)
            .withDescription('Normal (non-debug) sample interval.'),
    ],
    configure: async (device, coordinatorEndpoint) => {
        const ep = device.getEndpoint(1);
        await reporting.bind(ep, coordinatorEndpoint,
            ['genPowerCfg', 'msTemperatureMeasurement', 'msRelativeHumidity']);
        await reporting.temperature(ep, {min: 60, max: 300, change: 20});
        await reporting.humidity(ep, {min: 60, max: 300, change: 100});
        await reporting.batteryPercentageRemaining(ep,
            {min: 3600, max: 43200, change: 0});
        // Bind the debug cluster so debug_text/debug_status reports reach Z2M.
        await ep.bind(DEBUG_CLUSTER, coordinatorEndpoint);
    },
};
