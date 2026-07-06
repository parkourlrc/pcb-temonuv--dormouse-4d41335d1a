#ifndef FACTORY_RESET_H
#define FACTORY_RESET_H

// Power-cycle factory reset. This has no button in the BOM, so the recovery path
// is: cut power FACTORY_RESET_TRIGGER_COUNT times in a row, each within the short
// settle window, and the device wipes its Zigbee network and reboots un-joined so
// it can re-commission. A single reset (or a lone brownout that then runs past the
// settle window) clears the streak, so it will not trigger by accident.
//
// Call this once, first thing in application init.
void factory_reset_boot_check(void);

#endif  // FACTORY_RESET_H
