cmake_minimum_required(VERSION 3.20)

if (APPLE)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "Minimum OS X deployment version")
endif()

project(SinPunishmentRecompiled LANGUAGES C CXX)
set(CMAKE_C_STANDARD 17)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if (CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_CXX_SIMULATE_ID STREQUAL "MSVC")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wno-everything /W4")
endif()

if (WIN32)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -D_DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR")
endif()

if (APPLE)
    enable_language(OBJC OBJCXX)
endif()

if (CMAKE_VERSION VERSION_GREATER_EQUAL "3.24.0")
    cmake_policy(SET CMP0135 NEW)
endif()

set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

set(RT64_STATIC TRUE)
set(RT64_SDL_WINDOW_VULKAN TRUE)
add_compile_definitions(
    HLSL_CPU
    __PRFCHWINTRIN_H
)

# Make DXC/SPIRVCROSS and shader options visible to all subdirectories (recompui
# builds shaders with rt64's build_*_shader functions, which need these variables
# in the caller's scope).
set (DXC_COMMON_OPTS "-I${CMAKE_SOURCE_DIR}/lib/rt64/src")
set (DXC_DXIL_OPTS "-Wno-ignored-attributes")
set (DXC_SPV_OPTS "-spirv" "-fspv-target-env=vulkan1.0" "-fvk-use-dx-layout")
set (DXC_PS_OPTS "${DXC_COMMON_OPTS}" "-E" "PSMain" "-T ps_6_3")
set (DXC_VS_OPTS "${DXC_COMMON_OPTS}" "-E" "VSMain" "-T vs_6_3" "-fvk-invert-y")
set (DXC_CS_OPTS "${DXC_COMMON_OPTS}" "-E" "CSMain" "-T cs_6_3")
set (DXC_GS_OPTS "${DXC_COMMON_OPTS}" "-E" "GSMain" "-T gs_6_3")
set (DXC_LB_OPTS "${DXC_COMMON_OPTS}" "-D" "LIBRARY" "-T" "lib_6_3")
set (DXC_RT_OPTS "${DXC_COMMON_OPTS}" "-D" "RT_SHADER" "-T" "lib_6_3" "-fspv-target-env=vulkan1.1spirv1.4" "-fspv-extension=SPV_KHR_ray_tracing" "-fspv-extension=SPV_EXT_descriptor_indexing")
if (APPLE)
    if (CMAKE_SYSTEM_PROCESSOR STREQUAL "x86_64")
        set (DXC "DYLD_LIBRARY_PATH=${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/lib/x64" "${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/x64/dxc-macos")
        set (SPIRVCROSS "DYLD_LIBRARY_PATH=${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/spirv-cross/lib/x64:$ENV{DYLD_LIBRARY_PATH}" "${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/spirv-cross/bin/x64/spirv-cross")
    else()
        set (DXC "DYLD_LIBRARY_PATH=${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/lib/arm64" "${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/arm64/dxc-macos")
        set (SPIRVCROSS "DYLD_LIBRARY_PATH=${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/spirv-cross/lib/arm64:$ENV{DYLD_LIBRARY_PATH}" "${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/spirv-cross/bin/arm64/spirv-cross")
    endif()
endif()

add_subdirectory(${CMAKE_SOURCE_DIR}/lib/rt64 ${CMAKE_BINARY_DIR}/rt64)
if (APPLE)
    # hlslpp's scalar fallback uses labs() without including <stdlib.h>; some TUs
    # (e.g. rt64_preset_draw_call.cpp) fail on macOS/clang. Force-include it.
    target_compile_options(rt64 PRIVATE -include stdlib.h)
endif()
set(BUILD_SHARED_LIBS OFF)
add_subdirectory(${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime)
# RecompFrontend's subprojects (recompinput/recompui) expect these variables,
# normally set by lib/RecompFrontend/CMakeLists.txt. Since the root adds the
# subdirectories directly, provide them here (and find SDL2 before they
# configure so SDL2_INCLUDE_DIRS is available to them).
set(RECOMP_FRONTEND_N64MODERNRUNTIME_PATH "${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime")
set(RECOMP_FRONTEND_RT64_PATH "${CMAKE_SOURCE_DIR}/lib/rt64")
if (APPLE OR CMAKE_SYSTEM_NAME MATCHES "Linux")
    find_package(SDL2 REQUIRED)
endif()
add_subdirectory(${CMAKE_SOURCE_DIR}/lib/RecompFrontend/recompinput)
add_subdirectory(${CMAKE_SOURCE_DIR}/lib/RecompFrontend/recompui)

target_include_directories(rt64 PRIVATE ${CMAKE_BINARY_DIR}/rt64/src)

# ---------------------------------------------------------------------------
# Game targets. Only created once their sources exist:
#   - RecompiledFuncs/   <- scripts/recompile.sh output (needs symbols/, Phase 1)
#   - src/main|game/*    <- port code (Phase 2/3)
# Until then the tree still configures so the submodules can be built/verified.
# ---------------------------------------------------------------------------
file(GLOB FUNC_C_SOURCES ${CMAKE_SOURCE_DIR}/RecompiledFuncs/*.c)
file(GLOB FUNC_CXX_SOURCES ${CMAKE_SOURCE_DIR}/RecompiledFuncs/*.cpp)
set(HAS_PORT_SOURCES FALSE)
foreach(candidate
    ${CMAKE_SOURCE_DIR}/src/main/main.cpp
    ${CMAKE_SOURCE_DIR}/src/game/game.cpp
)
    if(EXISTS ${candidate})
        set(HAS_PORT_SOURCES TRUE)
    endif()
endforeach()

if (FUNC_C_SOURCES OR FUNC_CXX_SOURCES OR HAS_PORT_SOURCES)

    # RecompiledFuncs - primary recompiler output (only created once the
    # recompiler has produced sources, i.e. after Phase 1's recompile.sh).
    if (FUNC_C_SOURCES OR FUNC_CXX_SOURCES)
        add_library(RecompiledFuncs STATIC)
        target_compile_options(RecompiledFuncs PRIVATE
            -fno-strict-aliasing
            -Wno-unused-variable
            -Wno-implicit-function-declaration
            -falign-functions=16
        )
        target_include_directories(RecompiledFuncs PRIVATE
            ${CMAKE_SOURCE_DIR}/include
            ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/ultramodern/include
            ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/librecomp/include
            ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/N64Recomp/include
        )
        target_sources(RecompiledFuncs PRIVATE ${FUNC_C_SOURCES} ${FUNC_CXX_SOURCES})
    endif()

    # Main executable
    add_executable(SinPunishmentRecompiled)

    set(SOURCES)
    foreach(game_src
        ${CMAKE_SOURCE_DIR}/src/main/main.cpp
        ${CMAKE_SOURCE_DIR}/src/game/game.cpp
    )
        if(EXISTS ${game_src})
            list(APPEND SOURCES ${game_src})
        endif()
    endforeach()
    file(GLOB RSP_SOURCES ${CMAKE_SOURCE_DIR}/rsp/*.cpp)
    list(APPEND SOURCES ${RSP_SOURCES})

    target_sources(SinPunishmentRecompiled PRIVATE ${SOURCES})

    target_include_directories(SinPunishmentRecompiled PRIVATE
        ${CMAKE_SOURCE_DIR}/include
        ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/N64Recomp/include
        ${CMAKE_SOURCE_DIR}/lib/N64ModernRuntime/thirdparty/sse2neon
        ${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib
        ${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/hlslpp/include
        ${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/inc
        ${CMAKE_SOURCE_DIR}/lib/rt64/src
        ${CMAKE_SOURCE_DIR}/lib/rt64/src/rhi
        ${CMAKE_SOURCE_DIR}/lib/rt64/src/render
        ${CMAKE_SOURCE_DIR}/lib/RecompFrontend/recompinput/include
        ${CMAKE_SOURCE_DIR}/lib/RecompFrontend/recompui/include
        ${CMAKE_SOURCE_DIR}/lib/RecompFrontend/recompui/src
        ${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/nativefiledialog-extended/src/include
    )

    if(CMAKE_SIZEOF_VOID_P EQUAL 8 AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|amd64|AMD64")
        target_compile_options(SinPunishmentRecompiled PRIVATE
            -march=nehalem
            -fno-strict-aliasing
            -fms-extensions
        )
    else()
        target_compile_options(SinPunishmentRecompiled PRIVATE
            -fno-strict-aliasing
            -fms-extensions
        )
    endif()

    if (MSVC)
        # Disable identical code folding; breaks mod function patching.
        target_link_options(SinPunishmentRecompiled PRIVATE /OPT:NOICF)
    elseif (APPLE)
        # ld64 wrapper respecting segprot max_prot (required for mod patching).
        # See BanjoRecomp .github/macos/ld64 — enable when mods/patches land (Phase 3+).
        # target_link_options(SinPunishmentRecompiled PRIVATE
        #     "-fuse-ld=${CMAKE_SOURCE_DIR}/.github/macos/ld64")
    endif()

    if (WIN32)
        include(FetchContent)
        set(SDL2_VERSION "2.30.3")
        FetchContent_Declare(
            sdl2
            URL https://github.com/libsdl-org/SDL/releases/download/release-${SDL2_VERSION}/SDL2-devel-${SDL2_VERSION}-VC.zip
        )
        FetchContent_MakeAvailable(sdl2)
        target_include_directories(SinPunishmentRecompiled PRIVATE ${sdl2_SOURCE_DIR}/include)
        target_link_directories(SinPunishmentRecompiled PRIVATE ${sdl2_SOURCE_DIR}/lib/x64)
        add_custom_command(TARGET SinPunishmentRecompiled POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${sdl2_SOURCE_DIR}/lib/x64/SDL2.dll"
                "${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/x64/dxil.dll"
                "${CMAKE_SOURCE_DIR}/lib/rt64/src/contrib/dxc/bin/x64/dxcompiler.dll"
                $<TARGET_FILE_DIR:SinPunishmentRecompiled>)
        target_link_libraries(SinPunishmentRecompiled PRIVATE SDL2 Winmm.lib)
    endif()

    if (APPLE)
        find_package(SDL2 REQUIRED)
        target_include_directories(SinPunishmentRecompiled PRIVATE ${SDL2_INCLUDE_DIRS})
        set(CMAKE_THREAD_PREFER_PTHREAD TRUE)
        set(THREADS_PREFER_PTHREAD_FLAG TRUE)
        find_package(Threads REQUIRED)
        target_link_libraries(SinPunishmentRecompiled PRIVATE ${CMAKE_DL_LIBS} Threads::Threads SDL2::SDL2)
    endif()

    if (CMAKE_SYSTEM_NAME MATCHES "Linux")
        find_package(SDL2 REQUIRED)
        add_compile_definitions("PLUME_SDL_VULKAN_ENABLED")
        add_compile_definitions("RT64_SDL_WINDOW_VULKAN")
        target_include_directories(SinPunishmentRecompiled PRIVATE ${SDL2_INCLUDE_DIRS})
        find_package(Freetype REQUIRED)
        include_directories(${FREETYPE_LIBRARIES})
        target_link_libraries(SinPunishmentRecompiled PRIVATE ${FREETYPE_LIBRARIES} SDL2::SDL2)
        set(CMAKE_THREAD_PREFER_PTHREAD TRUE)
        set(THREADS_PREFER_PTHREAD_FLAG TRUE)
        find_package(Threads REQUIRED)
        target_link_libraries(SinPunishmentRecompiled PRIVATE "-latomic -static-libstdc++" ${CMAKE_DL_LIBS} Threads::Threads)
    endif()

    # RecompUI links against RT64's plume; keep link order stable.
    # RecompiledFuncs is only created once Phase 1's recompiler output exists.
    if (TARGET RecompiledFuncs)
        target_link_libraries(SinPunishmentRecompiled PRIVATE RecompiledFuncs)
    endif()
    target_link_libraries(SinPunishmentRecompiled PRIVATE
        recompui
        recompinput
        ultramodern
        librecomp
        rt64
    )

else()
    message(WARNING "Game sources not present yet (RecompiledFuncs/ empty, src/main|game missing). "
                    "Submodules build fine; game targets appear after Phase 1-2 of GOAL.md.")
endif()
