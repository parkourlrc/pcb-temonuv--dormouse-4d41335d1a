/*
 * factory_reset.c — button-less "power-cycle N times" factory reset.
 *
 * On each boot we bump a wear-levelled NVM3 counter. A settle event clears it
 * back to zero once the device has run long enough to count as a normal boot, so
 * only *quick, consecutive* power cycles accumulate. When the streak reaches
 * FACTORY_RESET_TRIGGER_COUNT we wipe the Zigbee network and reset — the device
 * comes back un-joined and re-commissions.
 *
 * Context note: NVM3 writes (flash) must run in app context, not an ISR. The
 * boot check runs from main-init (safe); the settle clear runs from a Zigbee AF
 * event (also app context) rather than a raw sleeptimer callback (ISR).
 *
 * Two symbols to confirm against your SDK build (flagged inline):
 *   - FACTORY_RESET_NVM3_KEY must not collide with a stack NVM3 key.
 *   - sl_zigbee_leave_network() is the current-SDK name for emberLeaveNetwork().
 */
#include "factory_reset.h"

#include "app/framework/include/af.h"
#include "sl_sleeptimer.h"         // sl_sleeptimer_delay_millisecond()
#include "nvm3_default.h"
#include "em_device.h"             // NVIC_SystemReset() (CMSIS core)

// Application NVM3 key. Stack/framework keys live in their own reserved ranges;
// VERIFY this one is free on your SDK generation before shipping.
#define FACTORY_RESET_NVM3_KEY      0x0004DE01u
#define FACTORY_RESET_TRIGGER_COUNT 5u        // quick power cycles -> reset
#define FACTORY_RESET_SETTLE_MS     3000u     // "ran long enough" == normal boot

static sl_zigbee_af_event_t settle_event;
static sl_zigbee_af_event_t reset_event;

static void reset_event_handler(sl_zigbee_af_event_t *event)
{
  (void)event;
  NVIC_SystemReset();
}

// Ran past the settle window => this was a normal boot; clear the streak. Runs
// in app (non-ISR) context, so the NVM3 write is safe.
static void settle_event_handler(sl_zigbee_af_event_t *event)
{
  (void)event;
  (void)nvm3_writeCounter(nvm3_defaultHandle, FACTORY_RESET_NVM3_KEY, 0);
}

void factory_reset_boot_check(void)
{
  uint32_t count = 0;

  // Increment the consecutive-power-cycle counter. On first ever use the key does
  // not exist yet, so create it at 1.
  if (nvm3_incrementCounter(nvm3_defaultHandle, FACTORY_RESET_NVM3_KEY, &count)
      != ECODE_NVM3_OK) {
    (void)nvm3_writeCounter(nvm3_defaultHandle, FACTORY_RESET_NVM3_KEY, 1);
    count = 1;
  }

  if (count >= FACTORY_RESET_TRIGGER_COUNT) {
    (void)nvm3_writeCounter(nvm3_defaultHandle, FACTORY_RESET_NVM3_KEY, 0);
    // Forget the network so we boot un-joined and re-commission. Broadcast the
    // leave (no silent option) so the parent/coordinator drops us cleanly.
    (void)sl_zigbee_leave_network(SL_ZIGBEE_LEAVE_NWK_WITH_NO_OPTION);
    
    // Schedule a reset to give the stack time to pump the leave packet over the air
    sl_zigbee_af_event_init(&reset_event, reset_event_handler);
    sl_zigbee_af_event_set_delay_ms(&reset_event, 500);
    return;
  }

  // Otherwise arm the settle event: survive FACTORY_RESET_SETTLE_MS and the
  // counter is cleared, so isolated resets/brownouts do not accumulate.
  sl_zigbee_af_event_init(&settle_event, settle_event_handler);
  sl_zigbee_af_event_set_delay_ms(&settle_event, FACTORY_RESET_SETTLE_MS);
}
