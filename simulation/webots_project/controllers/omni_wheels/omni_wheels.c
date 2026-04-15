/*
 * Copyright 1996-2024 Cyberbotics Ltd.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/*
 * Description: Demo of a FOUR-omni-wheels robot (Modified)
 * Original Author: Mehdi Ghanavati
 */

#include <stdio.h>
#include <webots/motor.h>
#include <webots/robot.h>

// Ubah array device menjadi 4
static WbDeviceTag wheels[4];

// Matrix perintah: [5 gerakan][4 kecepatan roda]
// Pola gerakan disesuaikan untuk konfigurasi 4 roda (Cross/+ configuration)
// Asumsi urutan roda: Depan, Kanan, Belakang, Kiri (atau sesuai urutan rotasi 0, 90, 180, 270)
static double cmd[5][4] = {
  {2, 0, -2, 0},    // Gerakan 1: Maju/Mundur (tergantung sumbu)
  {0, 2, 0, -2},    // Gerakan 2: Geser Kanan/Kiri
  {-2, 0, 2, 0},    // Gerakan 3: Lawan arah Gerakan 1
  {0, -2, 0, 2},    // Gerakan 4: Lawan arah Gerakan 2
  {2, 2, 2, 2},     // Gerakan 5: Berputar di tempat (Spin)
};

static double SPEED_FACTOR = 4.0;

int main() {
  int i, j, k;

  // initialize Webots
  wb_robot_init();

  // Loop 4 kali untuk inisialisasi wheel1, wheel2, wheel3, wheel4
  for (i = 0; i < 4; i++) {
    char name[64];
    sprintf(name, "wheel%d", i + 1);
    wheels[i] = wb_robot_get_device(name);
    wb_motor_set_position(wheels[i], INFINITY);
  }

  while (1) {
    for (i = 0; i < 5; i++) {
      // Loop 4 kali untuk mengirim command ke setiap roda
      for (j = 0; j < 4; j++)
        wb_motor_set_velocity(wheels[j], cmd[i][j] * SPEED_FACTOR);

      // Delay langkah simulasi
      for (k = 0; k < 100; k++)
        wb_robot_step(8);
    }
  }

  return 0;
}