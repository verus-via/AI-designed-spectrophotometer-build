// VS-SPEC-001 — Scanning colorimeter: optical body (design spec 0.1, rev D)
// + puck base for ESP32-C6 SuperMini. All units mm.
// Select part:  openscad -D 'part="body"' -o body.stl vs_body.scad
// parts: body, src_plate, det_plate, ring, lid, base_cup, base_deck, assembly
part = "assembly";
$fn = 96;
e = 0.01;

// ---------- Optical body (spec 0.1) ----------
L = 28.50; W = 23.00; H = 34.00;
ax_y = W/2; ax_z = 15.00;                 // optical axis
well = 13.00; well_x0 = 7.75; well_floor = 4.00;
bore_d = 5.20; bore_comp = 0.20;          // note 9: model bores 0.20 oversize
bore_len = 5.75;
ap_d = 2.50; ap_len = 2.00;               // aperture: NO compensation (note 5)
pilot_d = 1.70; pilot_dp = 6.00;          // M2 self-tap
screw_pts = [[3.5,3.0],[19.5,3.0],[3.5,30.0],[19.5,30.0]];  // [y,z], 16.00 ctrs
base_pilots = [3.5, 25.0];               // X stations, on centreline, underside
base_pilot_dp = 8.0;

module xcyl(d, x0, x1, y=ax_y, z=ax_z) {
  translate([x0, y, z]) rotate([0,90,0]) cylinder(d=d, h=x1-x0);
}

module body() {
  difference() {
    cube([L, W, H]);
    translate([well_x0, (W-well)/2, well_floor]) cube([well, well, H]);
    xcyl(bore_d+bore_comp, -1, bore_len);
    xcyl(ap_d, bore_len-e, well_x0+e);
    xcyl(ap_d, well_x0+well-e, L-bore_len+e);
    xcyl(bore_d+bore_comp, L-bore_len, L+1);
    for (p = screw_pts) {
      xcyl(pilot_d, -1, pilot_dp, p[0], p[1]);
      xcyl(pilot_d, L-pilot_dp, L+1, p[0], p[1]);
    }
    for (x = base_pilots) translate([x, ax_y, -1]) cylinder(d=pilot_d, h=base_pilot_dp+1);
  }
}

// ---------- End plates, rev B: fitted to the actual parts ----------
// Source: BTF-LIGHTING WS2812B on round heat-sink board (B01DC0J3UM), listed 10 mm x 3 mm
led_h = 1.57;                             // WS2812B package height
lb_d = 10.00; lb_clr = 0.20;              // round board diameter + radial clearance
lb_t = 3.00 - led_h;                      // board thickness implied by the 3 mm listing
src_t = 6.00;
lb_ch_dp = 1.50;                          // chamber behind board for rim-pad solder joints
lb_boss_d = 3.00;                            // back-stop on board centre
wire_off = 3.30;                          // wire hole centre below the axis
chan_w = 4.00;                            // internal wire channel to plate bottom
wire_hole_d = 3.40;                       // pass-through, wire cavity -> outer face
ogroove_w = 4.00; ogroove_dp = 2.00;      // wire channel on outer face, down to bottom edge

// Detector: Adafruit TSL2591 breakout (original, 0.75" x 0.65"), per Adafruit Eagle .brd
tb_L = 19.05; tb_W = 16.51; tb_t = 1.60;  // board: L along Z, W along Y
tb_sensor = [9.779, 9.525];               // TSL2591 die centre, board coords [x,y]
tb_holes = [[2.54,13.97],[16.51,13.97]];  // Ø2.5 plated mounting holes
tb_hdr_y = 2.54; tb_hdr_x = [3.175, 15.875]; // 6-pin header row (Vin..SCL)
comp_h = 1.30;                            // tallest front-side part (0805 10uF caps)
tb_clr = 0.25; peg_d = 2.10;
det_t = 6.00;
tb_pocket_dp = tb_t + comp_h + 0.10;
trench_w = 3.60; trench_dp = 1.50;
// board -> plate mapping: board x -> Z, board y -> Y (mirrored); sensor lands on axis
function tbZ(bx) = ax_z + (bx - tb_sensor[0]);
function tbY(by) = ax_y - (by - tb_sensor[1]);
sensor_window_x = L + comp_h - 0.65;      // DFN6 package is 0.65 tall

module src_plate() {
  pk_d = lb_d + 2*lb_clr;
  pk_dp = led_h + lb_t;                       // LED + its board; LED face flush at X=0
  xb = -pk_dp;                                // board back face
  wz = ax_z - wire_off;                       // wire hole height (below the back-stop boss)
  difference() {
    translate([-src_t, 0, 0]) cube([src_t, W, H]);
    xcyl(pk_d, -pk_dp, 1);                                    // round board pocket
    xcyl(pk_d, xb-lb_ch_dp, xb+e);                            // solder/wire chamber behind board
    // internal channel down to plate bottom
    translate([xb-lb_ch_dp, ax_y-chan_w/2, -1]) cube([lb_ch_dp, chan_w, ax_z+1]);
    // wire pass-through + outer-face channel down to bottom edge
    xcyl(wire_hole_d, -src_t-1, xb-lb_ch_dp+0.5, ax_y, wz);
    translate([-src_t-1, ax_y-ogroove_w/2, -1]) cube([ogroove_dp+1, ogroove_w, wz+1]);
    for (p = screw_pts) {
      xcyl(2.40, -src_t-1, 1, p[0], p[1]);
      xcyl(4.20, -src_t-1, -src_t+1.5, p[0], p[1]);
    }
  }
  // central back-stop boss against the bare centre of the board's back
  xcyl(lb_boss_d, xb-lb_ch_dp-e, xb);
}

module det_plate() {
  y0 = tbY(tb_W) - tb_clr; y1 = tbY(0) + tb_clr;
  z0 = tbZ(0) - tb_clr;    z1 = tbZ(tb_L) + tb_clr;
  hy = tbY(tb_hdr_y);
  difference() {
    translate([L, 0, 0]) cube([det_t, W, H]);
    // board pocket (component side faces the body)
    translate([L-e, y0, z0]) cube([tb_pocket_dp+e, y1-y0, z1-z0]);
    // wire trench behind the header row, running down and out the plate bottom
    translate([L+tb_pocket_dp-e, hy-trench_w/2, -1]) cube([trench_dp+e, trench_w, tbZ(tb_hdr_x[1])+2.5+1]);
    // wire pass-through behind the header row + outer-face channel down to bottom edge
    // (routed to the plate centreline so the outer channel clears the M2 counterbores)
    wz = tbZ(tb_sensor[0]);
    translate([L+tb_pocket_dp-e, ax_y, wz-wire_hole_d/2]) cube([trench_dp+e, hy-ax_y, wire_hole_d]);
    xcyl(wire_hole_d, L+tb_pocket_dp+trench_dp-0.5, L+det_t+1, ax_y, wz);
    translate([L+det_t-ogroove_dp, ax_y-ogroove_w/2, -1]) cube([ogroove_dp+1, ogroove_w, wz+1]);
    for (p = screw_pts) {
      xcyl(2.40, L-1, L+det_t+1, p[0], p[1]);
      xcyl(4.20, L+det_t-1.5, L+det_t+1, p[0], p[1]);
    }
  }
  // locating pegs through the two mounting holes -> puts the sensor on the axis
  for (h = tb_holes)
    translate([L+tb_pocket_dp, tbY(h[1]), tbZ(h[0])]) rotate([0,-90,0]) {
      cylinder(d=peg_d, h=tb_t-0.2);
      translate([0,0,tb_t-0.2-e]) cylinder(d1=peg_d, d2=peg_d-0.6, h=0.3);
    }
}

module ring() difference() { cylinder(d=5.15, h=3.58); translate([0,0,-1]) cylinder(d=3.50, h=6); }

// provisional lid (note 13): 28.50 x 23.00 x 3.00, 1.00 register lip into the well
module lid() {
  cube([L, W, 3.0]);
  lip = well - 0.40;
  translate([well_x0+0.20, (W-well)/2+0.20, 3.0-e]) cube([lip, lip, 1.0]);
}


// ---------- Cuvette cap (replaces flat lid): covers the 15 mm of cuvette above the body ----------
cuv_sz = 12.50; cuv_h = 45.00;            // standard macro cuvette
cap_cav = 13.60;                          // chimney bore (clears cuvette + top rim)
cap_head = 2.00;                          // headroom above cuvette top
cap_wall = 2.00; cap_top_t = 2.00;        // chimney wall, flange/roof thickness
skirt_dp = 4.00; skirt_wall = 1.60; skirt_clr = 0.25;
cap_rise = cuv_h - (H - well_floor) + cap_head;   // cavity height above body top = 17.0
module cap() {                            // modelled upright, body top at z=0
  fx0 = -src_t; fx1 = L + det_t;          // body + plates footprint along X
  ix0 = fx0 - skirt_clr; ix1 = fx1 + skirt_clr; iy0 = -skirt_clr; iy1 = W + skirt_clr;
  cx = well_x0 + well/2; cy = W/2;
  difference() {
    union() {
      // flange + skirt
      translate([ix0-skirt_wall, iy0-skirt_wall, -skirt_dp])
        cube([ix1-ix0+2*skirt_wall, iy1-iy0+2*skirt_wall, skirt_dp+cap_top_t]);
      // chimney
      translate([cx-cap_cav/2-cap_wall, cy-cap_cav/2-cap_wall, 0])
        cube([cap_cav+2*cap_wall, cap_cav+2*cap_wall, cap_rise+cap_top_t]);
    }
    // pocket that drops over the top of body + end plates
    translate([ix0, iy0, -skirt_dp-1]) cube([ix1-ix0, iy1-iy0, skirt_dp+1]);
    // lead-in chamfer on skirt
    translate([0,0,-skirt_dp-e]) hull() {
      translate([ix0-0.6, iy0-0.6, 0]) cube([ix1-ix0+1.2, iy1-iy0+1.2, e]);
      translate([ix0, iy0, 0.6]) cube([ix1-ix0, iy1-iy0, e]);
    }
    // cuvette bore
    translate([cx-cap_cav/2, cy-cap_cav/2, -1]) cube([cap_cav, cap_cav, cap_rise+1]);
  }
}

// ---------- Puck base ----------
R = 38.10;             // Ø76.2 (hockey puck)
H_total = 25.40;
deck_t = 3.00;
H_cup = H_total - deck_t;
wall = 2.00; floor_t = 2.00;
flat_x = 36.50;        // flat spot carrying the USB-C port
boss_r = 33.30; boss_d = 6.5; boss_pilot = 2.50; boss_angles = [60,180,300];

// ESP32-C6 SuperMini (measure yours!)
brd_len = 25.60; brd_w = 18.00; brd_t = 1.00;
brd_lift = 3.00;                  // board underside above floor
usb_overhang = 0.60;              // receptacle lip beyond PCB edge
usb_h = 3.26;                     // receptacle height above PCB
brd_x1 = flat_x - wall;           // USB edge of board butts inner flat wall
brd_x0 = brd_x1 - brd_len;
brd_z0 = floor_t + brd_lift;
usb_zc = brd_z0 + brd_t + usb_h/2;

module outline(r, fx) intersection() { circle(r=r); translate([-2*r, -2*r]) square([2*r+fx, 4*r]); }
module stadium_x(w, h, x0, x1, zc) {   // stadium profile in YZ, extruded along X
  translate([x0, 0, zc]) rotate([0,90,0]) hull() {
    translate([0, -(w-h)/2, 0]) cylinder(d=h, h=x1-x0);
    translate([0,  (w-h)/2, 0]) cylinder(d=h, h=x1-x0);
  }
}

module base_cup() {
  difference() {
    union() {
      difference() {
        linear_extrude(H_cup) outline(R, flat_x);
        translate([0,0,floor_t]) linear_extrude(H_cup) outline(R-wall, flat_x-wall);
      }
      // screw bosses merged into wall
      intersection() {
        linear_extrude(H_cup) outline(R-0.5, flat_x);
        for (a = boss_angles) rotate([0,0,a]) translate([boss_r,0,0]) cylinder(d=boss_d, h=H_cup);
      }
      // board support rails (under the board centre, clear of the pin rows)
      for (y = [-4.5, 4.5]) translate([brd_x0+0.6, y-0.8, floor_t-e]) cube([brd_len-1.2, 1.6, brd_lift+e]);
      // side guides (stop below board top so edge pads stay clear)
      for (s = [-1, 1]) translate([brd_x0+3, s>0 ? brd_w/2+0.30 : -brd_w/2-0.30-1.2, floor_t-e])
        cube([brd_len-6, 1.2, brd_lift+brd_t*0.8+e]);
      // rear snap hook over the antenna end
      hook_x1 = brd_x0 - 0.25;
      translate([hook_x1-1.4, -3, floor_t-e]) cube([1.4, 6, brd_lift+brd_t+0.25+e]);
      translate([hook_x1-1.4, -3, brd_z0+brd_t+0.25]) hull() {
        cube([1.4+0.9, 6, 0.6]);
        translate([0,0,1.2]) cube([1.4, 6, e]);
      }
    }
    // boss pilots
    for (a = boss_angles) rotate([0,0,a]) translate([boss_r,0,H_cup-12]) cylinder(d=boss_pilot, h=13);
    // USB-C: receptacle slot through flat wall + outer relief for the plug overmold
    stadium_x(9.60, 4.00, brd_x1-1, flat_x+1, usb_zc);
    stadium_x(13.50, 8.00, brd_x1+usb_overhang, flat_x+1, usb_zc);
  }
}

// body placement on deck: optical axis along +Y (detector toward +Y)
foot_len = L + src_t + det_t;                  // body + both plates
foot_c = (L + det_t - src_t)/2;                // footprint centre in body X
module place_body() translate([W/2, -foot_c, H_total]) rotate([0,0,90]) children();
// local (x,y,z) -> puck (-(y-11.5) .. ) handled by rotate; helper for holes:
function pk(xl, yl) = [-(yl - W/2), xl - foot_c];

module slot_local(x0, x1, y0, y1) {
  m = 0.75;
  a = pk(x0-m, y0-m); b = pk(x1+m, y1+m);
  translate([min(a[0],b[0]), min(a[1],b[1]), H_cup-1]) cube([abs(b[0]-a[0]), abs(b[1]-a[1]), deck_t+2]);
}
module base_deck() {
  difference() {
    translate([0,0,H_cup]) linear_extrude(deck_t) outline(R, flat_x);
    // locating pocket for body + both end plates
    translate([-(W+0.4)/2, -(foot_len+0.4)/2, H_total-1.0]) cube([W+0.4, foot_len+0.4, 2]);
    // M3 countersunk clearance at bosses
    for (a = boss_angles) rotate([0,0,a]) translate([boss_r,0,H_cup-1]) {
      cylinder(d=3.4, h=deck_t+2);
      translate([0,0,1+deck_t-1.7]) cylinder(d1=3.4, d2=6.6, h=1.7+e);
    }
    // M2 clearance for body underside pilots (screw up from inside the cup)
    for (x = base_pilots) translate(concat(pk(x, ax_y), [H_cup-1])) cylinder(d=2.4, h=deck_t+2);
    // wire slots under each plate's internal channel (0.75 margin)
    // source: under the internal channel and the outer-face channel
    slot_local(-src_t-1.5, -led_h-lb_t, ax_y-max(chan_w,ogroove_w)/2, ax_y+max(chan_w,ogroove_w)/2);
    // detector: behind the header row
    slot_local(L+tb_pocket_dp, L+tb_pocket_dp+trench_dp, tbY(tb_hdr_y)-trench_w/2, tbY(tb_hdr_y)+trench_w/2);
    slot_local(L+det_t-ogroove_dp, L+det_t+1.5, ax_y-ogroove_w/2, ax_y+ogroove_w/2);
  }
}

module assembly() {
  color("dimgray") base_cup();
  color("gray") base_deck();
  place_body() {
    color("black") body();
    color("darkslategray") src_plate();
    color("darkslategray") det_plate();
    translate([0,0,H]) color("dimgray") cap();
  }
}

// ---------- print-orientation exports ----------
if (part == "body") body();
if (part == "src_plate") translate([0,0,src_t]) rotate([0,-90,0]) src_plate();       // outer face down
if (part == "det_plate") translate([0,0,L+det_t]) rotate([0,90,0]) det_plate();      // outer face down
if (part == "ring") for (i=[0,1]) translate([i*8,0,0]) ring();
if (part == "lid") lid();                                                               // (superseded by cap)
if (part == "cap") translate([0,0,skirt_dp]) cap();                                     // print upright, skirt on bed
if (part == "base_cup") base_cup();
if (part == "base_deck") translate([0,0,-H_cup]) base_deck();
if (part == "assembly") assembly();
